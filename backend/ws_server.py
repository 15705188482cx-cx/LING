# -*- coding: utf-8 -*-
"""WebSocket 语音通话服务 - V0.3 全双工流式 + VAD + Opus + 实时打断。

独立进程 :8766。借鉴 xiaozhi-esp32-server 架构：
  - SileroVAD 服务端自动断句（auto 模式，说完 0.8s 自动响应）
  - 双向 Opus 编解码（16kHz/mono/60ms 帧/24kbps，省 10x 带宽）
  - TTS 流式分段（整句 WAV→PCM→Opus 60ms 包逐包发，边合成边播）
  - sentence_id 轮次隔离（打断后旧轮残留靠 id 不匹配丢弃）
  - 实时打断（每个 Opus 包发送前检查 abort_flag，60ms 颗粒度）

协议（V0.3）：
  上行 JSON：
    {"type":"hello","mode":"auto","sample_rate":16000}  握手+模式(auto/manual)
    {"type":"start"}                                      manual 模式开始录音
    {"type":"stop","sample_rate":16000}                   manual 模式结束录音
    {"type":"abort"}                                      打断她的话
    {"type":"video_frame","image":"<base64>"}             视频帧（视频通话）
  上行二进制：Opus 包（60ms/960样本）或 WAV/PCM（manual 兼容）

  下行 JSON：
    {"type":"ready","session_id":"..."}
    {"type":"asr_text","text":"...","sentence_id":"..."}
    {"type":"llm_chunk","text":"...","sentence_id":"..."}
    {"type":"emotion","emotion":"撒娇","sentence_id":"..."}
    {"type":"tts_start","sentence_id":"..."}
    {"type":"tts_stop","sentence_id":"..."}               打断/结束，前端停播
    {"type":"done","sentence_id":"..."}
  下行二进制：Opus 包（TTS 音频流）

启动：
  python ws_server.py
"""
import asyncio
import base64
import json
import logging
import struct
import wave
import io
import uuid
from contextlib import suppress

import httpx
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import config
from core import LingBackend
from asr import ASR
from vad import VAD
from opus_codec import OpusEncoder, OpusDecoder, wav_bytes_to_pcm, OPUS_FRAME_MS
import tts_cache

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# 启动时加载（与 api_server 各自独立实例，共享同一份 SQLite/FAISS）
backend = LingBackend()
asr = ASR()
vad = VAD(
    threshold=config.VAD_THRESHOLD,
    threshold_low=config.VAD_THRESHOLD_LOW,
    silence_ms=config.VAD_SILENCE_MS,
)

TTS_URL = config.LIUJIALING_URL
TTS_STREAMING_URL = config.TTS_STREAMING_URL
TTS_STREAMING_MODE = config.TTS_STREAMING_MODE
# 流式 TTS 输出采样率（api_v2 固定 32000，需重采样到 16kHz 喂 Opus）
_TTS_STREAM_SAMPLE_RATE = 32000
_OPUS_SAMPLE_RATE = 16000

app = FastAPI(title="Ling WS + ASR + VAD")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AsrRequest(BaseModel):
    audio: str
    sample_rate: int = 16000


@app.post("/asr")
def asr_transcribe(req: AsrRequest):
    """HTTP ASR 端点（按住说话用）：base64 WAV → {text}。"""
    try:
        wav_bytes = base64.b64decode(req.audio)
        try:
            with wave.open(io.BytesIO(wav_bytes), "rb") as w:
                pcm = w.readframes(w.getnframes())
                sr = w.getframerate()
        except Exception:
            pcm = wav_bytes
            sr = req.sample_rate
        text = asr.transcribe(pcm, sample_rate=sr)
        return {"text": text}
    except Exception as e:
        logger.exception("/asr 失败")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/health")
def health():
    return {"status": "ok", "asr": asr.enabled, "vad": True}


async def tts_synthesize(text: str) -> bytes:
    """调 :8880 合成 wav，返回字节。"""
    async with httpx.AsyncClient() as client:
        resp = await client.post(TTS_URL, json={"text": text.strip()}, timeout=60.0)
        resp.raise_for_status()
        return resp.content


def _resample_pcm_32k_to_16k(pcm_32k: bytes) -> bytes:
    """32kHz int16 PCM → 16kHz int16 PCM（scipy 多相滤波器重采样）。

    api_v2.py 流式输出固定 32kHz，Opus 编码器要 16kHz，需逐 chunk 重采样。
    调用方负责保证 pcm_32k 是 2 字节对齐（int16），奇数字节尾巴由调用方暂存拼接。
    """
    import numpy as np
    import scipy.signal
    from math import gcd

    if not pcm_32k or len(pcm_32k) < 2:
        return b""
    # 防御性裁剪（调用方已对齐，这里只兜底）
    usable = len(pcm_32k) - (len(pcm_32k) % 2)
    samples = np.frombuffer(pcm_32k[:usable], dtype=np.int16).astype(np.float32) / 32768.0
    g = gcd(_TTS_STREAM_SAMPLE_RATE, _OPUS_SAMPLE_RATE)
    up, down = _OPUS_SAMPLE_RATE // g, _TTS_STREAM_SAMPLE_RATE // g
    resampled = scipy.signal.resample_poly(samples, up, down)
    return (resampled * 32768.0).astype(np.int16).tobytes()


async def tts_synthesize_stream(text: str):
    """流式合成：调 :9880 streaming_mode=1，异步 yield 16kHz PCM bytes 块。

    边合成边返回 PCM chunk（已剥 44 字节 WAV 头 + 重采样到 16kHz），
    调用方可边收边 Opus 编码发送，首字延迟从整句 ~2s 降到首包 ~1.2s。

    流式不可用（连接失败）时返回 None，调用方回退整句合成。
    """
    payload = {
        "text": text.strip(),
        "text_lang": "zh",
        "ref_audio_path": config.TTS_REF_AUDIO,
        "prompt_text": config.TTS_REF_TEXT,
        "prompt_lang": "zh",
        "top_p": 1,
        "temperature": 1,
        "speed_factor": 0.93,
        "media_type": "wav",
        "streaming_mode": TTS_STREAMING_MODE,
    }
    try:
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST", TTS_STREAMING_URL, json=payload, timeout=120.0
            ) as resp:
                resp.raise_for_status()
                first_chunk = True
                leftover = b""  # 上个 chunk 奇数字节尾巴（int16 对齐用）
                async for chunk in resp.aiter_bytes():
                    if not chunk:
                        continue
                    if first_chunk:
                        # 首包是 44 字节 WAV 头，剥掉
                        if len(chunk) >= 44 and chunk[:4] == b"RIFF":
                            chunk = chunk[44:]
                        first_chunk = False
                        if not chunk:
                            continue
                    # 拼上上次遗留的奇数字节，保证 int16 对齐
                    chunk = leftover + chunk
                    usable = len(chunk) - (len(chunk) % 2)
                    leftover = chunk[usable:]
                    chunk = chunk[:usable]
                    if not chunk:
                        continue
                    # 32kHz PCM → 16kHz PCM
                    pcm_16k = _resample_pcm_32k_to_16k(chunk)
                    if pcm_16k:
                        yield pcm_16k
    except (httpx.ConnectError, httpx.ConnectTimeout) as e:
        logger.warning(f"流式 TTS 不可用，将回退整句合成: {e}")
        return  # StopAsyncIteration
    except Exception as e:
        logger.error(f"流式 TTS 异常: {e}")
        return


# TTS 缓存预热：后台异步合成高频短回复（"在呢"/"嗯嗯"等），命中时 0ms
# 优先用流式 :9880 的非流式模式预热（:8880 没起时也能工作）；失败静默跳过
async def _warmup_synthesize(text: str) -> bytes:
    """预热用合成函数：走 :9880 streaming_mode=0 拿整段 WAV。"""
    payload = {
        "text": text.strip(),
        "text_lang": "zh",
        "ref_audio_path": config.TTS_REF_AUDIO,
        "prompt_text": config.TTS_REF_TEXT,
        "prompt_lang": "zh",
        "top_p": 1,
        "temperature": 1,
        "speed_factor": 0.93,
        "media_type": "wav",
        "streaming_mode": 0,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(TTS_STREAMING_URL, json=payload, timeout=60.0)
        resp.raise_for_status()
        return resp.content


tts_cache.warmup(_warmup_synthesize)


def parse_wav_to_pcm(wav_bytes: bytes) -> tuple[bytes, int]:
    """WAV bytes → (pcm_bytes, sample_rate)。兼容裸 PCM。"""
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as w:
            return w.readframes(w.getnframes()), w.getframerate()
    except Exception:
        return wav_bytes, 16000


@app.websocket("/ws/voice")
async def handle_connection(websocket: WebSocket):
    """单个 WebSocket 连接的处理循环（V0.3 全双工）。"""
    await websocket.accept()
    logger.info(f"WS 连接建立: {websocket.client}")

    # ---- per-connection 状态 ----
    session_id = uuid.uuid4().hex[:12]
    mode = "auto"  # auto=VAD 自动断句, manual=前端 start/stop
    current_sample_rate = 16000

    # auto 模式：VAD 状态 + 音频累积
    vad_state = vad.new_state()
    auto_audio_buffer = bytearray()  # 累积有声段 PCM（断句后送 ASR）

    # manual 模式：兼容旧逻辑
    manual_audio_buffer = bytearray()

    # Opus 解码器（上行，每连接一个）
    opus_decoder = OpusDecoder()

    # 轮次管理
    abort_flag = asyncio.Event()
    turn_task: asyncio.Task | None = None
    current_sentence_id: str | None = None
    latest_frame: str | None = None  # 最新视频帧 base64

    async def cancel_turn(reason: str) -> None:
        """打断当前轮次：设标志 + 取消 task + 通知前端停播。"""
        nonlocal turn_task, current_sentence_id
        abort_flag.set()
        if turn_task and not turn_task.done():
            turn_task.cancel()
            with suppress(asyncio.CancelledError):
                await turn_task
        turn_task = None
        # 通知前端立即停 TTS 播放
        if current_sentence_id:
            await websocket.send_json(
                {"type": "tts_stop", "sentence_id": current_sentence_id, "reason": reason}
            )
        current_sentence_id = None

    async def start_new_turn(audio_pcm: bytes, sample_rate: int) -> None:
        """开新一轮：生成 sentence_id + 启动 process_turn。"""
        nonlocal turn_task, current_sentence_id, abort_flag
        # 如果上一轮还没结束，先打断
        if turn_task and not turn_task.done():
            await cancel_turn("superseded")
        current_sentence_id = uuid.uuid4().hex[:12]
        abort_flag = asyncio.Event()
        turn_task = asyncio.create_task(
            process_turn(
                websocket, audio_pcm, sample_rate, abort_flag,
                current_sentence_id, latest_frame
            )
        )

    try:
        while True:
            message = await websocket.receive()

            # ---- 二进制帧 = 音频 ----
            if "bytes" in message and message["bytes"]:
                audio_data = message["bytes"]

                if mode == "auto":
                    # auto 模式：Opus 解码 → PCM → VAD → 累积有声段
                    pcm = opus_decoder.decode(audio_data)
                    if pcm:
                        vad.is_vad(pcm, vad_state)
                        auto_audio_buffer.extend(pcm)
                        # VAD 检测到端点 → 自动触发新一轮
                        if vad.detect_endpoint(vad_state) and len(auto_audio_buffer) > 3200:
                            # 至少 0.1s 音频才处理，避免纯噪触发
                            turn_pcm = bytes(auto_audio_buffer)
                            auto_audio_buffer.clear()
                            vad.reset_for_new_turn(vad_state)
                            await start_new_turn(turn_pcm, current_sample_rate)
                else:
                    # manual 模式：兼容旧逻辑，原样累积（可能是 WAV 或 PCM）
                    manual_audio_buffer.extend(audio_data)
                continue

            # ---- 文本帧 = JSON 控制消息 ----
            text = message.get("text")
            if not text:
                continue
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type")

            if msg_type == "hello":
                # V0.3 握手：上报模式 + 采样率
                mode = data.get("mode", "auto")
                current_sample_rate = data.get("sample_rate", 16000)
                await websocket.send_json({"type": "ready", "session_id": session_id})
                logger.info(f"[{session_id}] 握手 mode={mode} sr={current_sample_rate}")

            elif msg_type == "start":
                # manual 模式开始（兼容旧前端）
                if turn_task and not turn_task.done():
                    await cancel_turn("superseded")
                manual_audio_buffer.clear()
                abort_flag.clear()
                current_sample_rate = data.get("sample_rate", current_sample_rate)
                if mode == "manual":
                    await websocket.send_json({"type": "ready", "session_id": session_id})

            elif msg_type == "stop":
                # manual 模式结束录音，触发处理
                if mode != "manual":
                    continue  # auto 模式忽略 stop
                current_sample_rate = data.get("sample_rate", current_sample_rate)
                turn_audio = bytes(manual_audio_buffer)
                manual_audio_buffer.clear()
                if turn_audio:
                    await start_new_turn(turn_audio, current_sample_rate)

            elif msg_type == "abort":
                await cancel_turn("aborted")
                # auto 模式打断后重置 VAD，准备接下一句
                if mode == "auto":
                    vad.reset_for_new_turn(vad_state)
                    auto_audio_buffer.clear()
                logger.info(f"[{session_id}] 收到打断信号")

            elif msg_type == "video_frame":
                # 空帧（摄像头关闭）置 None，避免 VLM 用旧帧
                frame = data.get("image") or ""
                latest_frame = frame if frame else None

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WS 异常")
    finally:
        abort_flag.set()
        if turn_task and not turn_task.done():
            turn_task.cancel()
            with suppress(asyncio.CancelledError):
                await turn_task
        logger.info(f"WS 连接关闭: {websocket.client}")


async def _send_opus_packets(
    websocket: WebSocket,
    opus_packets: list[bytes],
    abort_flag: asyncio.Event,
    sentence_id: str,
) -> None:
    """整句 Opus 包逐包发送（路径 A/C 共用），含流控 + 打断检查。"""
    if not opus_packets:
        logger.warning(f"[{sentence_id}] TTS PCM 为空，跳过")
        return
    for i, pkt in enumerate(opus_packets):
        if abort_flag.is_set():
            logger.info(f"[{sentence_id}] TTS 被打断（包间 i={i}），停止发送")
            break
        await websocket.send_bytes(pkt)
        if i >= 5:
            await asyncio.sleep(OPUS_FRAME_MS / 1000)
    await websocket.send_json({"type": "tts_stop", "sentence_id": sentence_id})


async def process_turn(
    websocket: WebSocket,
    audio_bytes: bytes,
    sample_rate: int,
    abort_flag: asyncio.Event,
    sentence_id: str,
    frame_b64: str = None,
):
    """处理一轮：音频→ASR→[VLM]→LLM流式→TTS分段Opus→逐包回传。

    V0.3 改动：
    - TTS 从「整句 WAV 一次性发」改成「PCM→Opus 60ms 包逐包发」
    - 每个 Opus 包发送前检查 abort_flag（60ms 颗粒度打断）
    - 所有下行消息带 sentence_id
    """
    loop = asyncio.get_event_loop()

    # 1. 解析音频 + ASR + VLM 并行（两者无依赖：ASR 识别音频，VLM 看画面）
    # auto 模式 audio_bytes 是裸 PCM；manual 模式可能是 WAV
    if audio_bytes[:4] == b"RIFF":
        pcm, sr = parse_wav_to_pcm(audio_bytes)
    else:
        pcm, sr = audio_bytes, sample_rate

    if not pcm:
        await websocket.send_json({"type": "done", "sentence_id": sentence_id, "reason": "empty_audio"})
        return

    # ASR 和 VLM 并行启动（VLM 看帧，ASR 识别音频，互不依赖）
    # 原 V0.2 串行链路 ASR(400ms)→VLM(500ms-1s) 改为并行，省 VLM 全部延迟
    asr_task = loop.run_in_executor(None, asr.transcribe, pcm, sr)
    vlm_task = (
        loop.run_in_executor(None, backend.describe_vision, frame_b64)
        if frame_b64
        else None
    )

    user_text = await asr_task
    if not user_text:
        # ASR 空：取消可能还在跑的 VLM 任务（无害）
        if vlm_task and not vlm_task.done():
            vlm_task.cancel()
        await websocket.send_json({"type": "done", "sentence_id": sentence_id, "reason": "asr_empty"})
        return

    await websocket.send_json({"type": "asr_text", "text": user_text, "sentence_id": sentence_id})
    logger.info(f"[{sentence_id}] ASR: {user_text}")

    # VLM 等结果（并行已在 ASR 期间跑），超时 1.5s 跳过不阻塞 LLM
    if vlm_task:
        try:
            desc = await asyncio.wait_for(vlm_task, timeout=1.5)
            if desc:
                user_text = f"[我看到你{desc}] {user_text}"
                logger.info(f"[{sentence_id}] VLM 注入: {desc[:40]}")
        except asyncio.TimeoutError:
            logger.warning(f"[{sentence_id}] VLM 超时(1.5s)，跳过视觉注入")
            vlm_task.cancel()
        except Exception as e:
            logger.warning(f"[{sentence_id}] VLM 异常，跳过: {e}")

    # 2. 流式 LLM + 逐句 TTS（分段 Opus）
    import queue
    q = queue.Queue()

    def run_stream():
        try:
            for sentence, emotion in backend.chat_stream(user_text):
                q.put((sentence, emotion))
        except Exception as e:
            q.put(("__error__", str(e)))
        q.put(("__done__", None))

    loop.run_in_executor(None, run_stream)

    while True:
        item = await loop.run_in_executor(None, q.get)
        sentence, emotion = item

        if sentence == "__error__":
            logger.error(f"[{sentence_id}] chat_stream 错误: {emotion}")
            break
        if sentence == "__done__":
            break

        # emotion 信号（初始 "" + 最终 None，都带 emotion 无 sentence）
        if emotion and not sentence:
            await websocket.send_json(
                {"type": "emotion", "emotion": emotion, "sentence_id": sentence_id}
            )
            continue

        # 文本句
        if sentence:
            await websocket.send_json(
                {"type": "llm_chunk", "text": sentence, "sentence_id": sentence_id}
            )

            # 句间检查打断
            if abort_flag.is_set():
                logger.info(f"[{sentence_id}] TTS 被打断（句间），跳过剩余")
                break

            # 3. 这句送 TTS 合成 → PCM → Opus 60ms 包逐包发
            try:
                await websocket.send_json({"type": "tts_start", "sentence_id": sentence_id})

                # 先查 TTS 缓存：短回复命中时跳过合成+编码，0ms 出包
                cached_packets = tts_cache.get(sentence)
                if cached_packets:
                    # 路径 A：缓存命中，整句 Opus 包直发
                    logger.info(f"[{sentence_id}] TTS 缓存命中: '{sentence[:20]}'")
                    for i, pkt in enumerate(cached_packets):
                        if abort_flag.is_set():
                            logger.info(f"[{sentence_id}] TTS 被打断（包间 i={i}），停止发送")
                            break
                        await websocket.send_bytes(pkt)
                        if i >= 5:
                            await asyncio.sleep(OPUS_FRAME_MS / 1000)
                    await websocket.send_json({"type": "tts_stop", "sentence_id": sentence_id})
                elif TTS_STREAMING_URL:
                    # 路径 B：流式合成，边收 PCM 边 Opus 编码发送（首包延迟 ~1.2s）
                    streamed = False
                    encoder = OpusEncoder()
                    sent_count = 0

                    async for pcm_16k in tts_synthesize_stream(sentence):
                        if abort_flag.is_set():
                            logger.info(f"[{sentence_id}] TTS 被打断（流式中），停止发送")
                            break
                        # PCM chunk → Opus 包（encoder 内部按 960 样本帧切分）
                        new_packets: list[bytes] = []
                        encoder.encode(pcm_16k, callback=new_packets.append)
                        for pkt in new_packets:
                            if abort_flag.is_set():
                                break
                            await websocket.send_bytes(pkt)
                            sent_count += 1
                            # 前 5 包直发，第 6 包起按 60ms 节奏（防客户端缓冲溢出）
                            if sent_count >= 5:
                                await asyncio.sleep(OPUS_FRAME_MS / 1000)
                        streamed = True
                    # 刷出 encoder 缓冲区残余（不足一帧的尾部补零编出最后一包）
                    if not abort_flag.is_set():
                        tail: list[bytes] = []
                        encoder.encode(b"", callback=tail.append, end_of_stream=True)
                        for pkt in tail:
                            if abort_flag.is_set():
                                break
                            await websocket.send_bytes(pkt)
                    encoder.reset()
                    if streamed:
                        logger.info(f"[{sentence_id}] TTS 流式合成完成，共发 {sent_count} 包")
                        await websocket.send_json({"type": "tts_stop", "sentence_id": sentence_id})
                    else:
                        # 流式不可用（连接失败），回退整句合成
                        logger.info(f"[{sentence_id}] 流式不可用，回退整句合成")
                        wav_bytes = await tts_synthesize(sentence)
                        opus_packets = tts_cache.encode_and_cache(sentence, wav_bytes)
                        await _send_opus_packets(
                            websocket, opus_packets, abort_flag, sentence_id
                        )
                else:
                    # 路径 C：无流式，整句合成（原逻辑）
                    wav_bytes = await tts_synthesize(sentence)
                    opus_packets = tts_cache.encode_and_cache(sentence, wav_bytes)
                    await _send_opus_packets(
                        websocket, opus_packets, abort_flag, sentence_id
                    )
            except Exception as e:
                logger.error(f"[{sentence_id}] TTS 失败: {e}")

    # 本轮结束
    await websocket.send_json({"type": "done", "sentence_id": sentence_id})


if __name__ == "__main__":
    logger.info(
        f"WS 语音服务启动 :{config.WS_PORT} "
        f"(VAD silence={config.VAD_SILENCE_MS}ms, Opus 60ms/24kbps)"
    )
    uvicorn.run(app, host="0.0.0.0", port=config.WS_PORT)
