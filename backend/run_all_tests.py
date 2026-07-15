# -*- coding: utf-8 -*-
"""刘嘉玲 AI 伴侣 — 全流程闭环测试。

执行：python run_all_tests.py
覆盖 TEST_PLAN.md 的 A-F 全部用例，串行跑，实时打印 PASS/FAIL，末尾汇总。
"""
import asyncio
import base64
import io
import json
import os
import sys
import time
import wave

import requests
import websockets

# ---------- 配置 ----------
API = "http://127.0.0.1:8765"
WS = "ws://127.0.0.1:8766"
WS_DIRECT_ASR = "http://127.0.0.1:8766"
TTS = "http://127.0.0.1:8880"
HERE = os.path.dirname(os.path.abspath(__file__))
WAV_PATH = os.path.join(HERE, "test_full.wav")
IMG_PATH = os.path.join(HERE, "stickers", "撒娇", "撒娇.png")

# ---------- 结果收集 ----------
results = []  # [(id, name, ok, detail)]


def record(tid: str, name: str, ok: bool, detail: str = ""):
    mark = "✅ PASS" if ok else "❌ FAIL"
    line = f"{mark} [{tid}] {name}"
    if detail:
        line += f"  — {detail}"
    print(line)
    results.append((tid, name, ok, detail))


def section(title: str):
    print("\n" + "=" * 64)
    print(f"  {title}")
    print("=" * 64)


def load_wav_b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def load_img_b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def wav_info(path: str) -> str:
    w = wave.open(path, "rb")
    info = f"{w.getframerate()}Hz {w.getnchannels()}ch {w.getsampwidth()*8}bit {w.getnframes()/w.getframerate():.1f}s"
    w.close()
    return info


# ============================================================
# A. 环境冒烟
# ============================================================
def test_A():
    section("A. 环境冒烟")

    # A1 三服务 health
    try:
        r1 = requests.get(f"{API}/health", timeout=10).json()
        r2 = requests.get(f"{WS_DIRECT_ASR}/health", timeout=10).json()
        r3 = requests.get(f"{TTS}/health", timeout=10).json()
        ok = (r1.get("status") == "ok" and r1.get("memory") and r1.get("db")
              and r2.get("status") == "ok" and r2.get("asr")
              and r3.get("status") == "ok")
        record("A1", "三服务 health 检查", ok,
               f"api={r1.get('status')} ws={r2.get('status')} tts={r3.get('status')}")
    except Exception as e:
        record("A1", "三服务 health 检查", False, str(e))

    # A2 api_server → ws_server /asr 代理链路
    try:
        audio_b64 = load_wav_b64(WAV_PATH)
        r = requests.post(f"{API}/asr", json={"audio": audio_b64, "sample_rate": 32000}, timeout=30)
        text = r.json().get("text", "")
        ok = r.status_code == 200 and len(text) > 0
        record("A2", "api→ws /asr 代理链路", ok, f"识别: {text[:30]}")
    except Exception as e:
        record("A2", "api→ws /asr 代理链路", False, str(e))

    # A3 tts_server 合成可用
    try:
        r = requests.post(f"{TTS}/v1/audio/speech", json={"text": "测试合成"}, timeout=60)
        ok = r.status_code == 200 and len(r.content) > 1000 and r.headers.get("content-type", "").startswith("audio")
        record("A3", "tts_server 合成可用", ok, f"{len(r.content)} bytes {r.headers.get('content-type','')}")
    except Exception as e:
        record("A3", "tts_server 合成可用", False, str(e))


# ============================================================
# B. HTTP 接口测试
# ============================================================
def test_B():
    section("B. HTTP 接口测试 (api_server :8765)")

    # B1 /health
    try:
        r = requests.get(f"{API}/health", timeout=10).json()
        ok = r.get("status") == "ok" and "user_id" in r
        record("B1", "GET /health", ok, str(r))
    except Exception as e:
        record("B1", "GET /health", False, str(e))

    # B2 /chat 文字对话
    try:
        r = requests.post(f"{API}/chat", json={"text": "在吗？想你了"}, timeout=60).json()
        ok = bool(r.get("reply")) and r.get("emotion") in ["日常", "调情", "撒娇", "焦急", "冷淡"]
        record("B2", "POST /chat 文字对话", ok,
               f"emotion={r.get('emotion')} reply={r.get('reply','')[:40]!r}")
    except Exception as e:
        record("B2", "POST /chat 文字对话", False, str(e))

    # B3 /chat/image 图片对话
    try:
        img_b64 = load_img_b64(IMG_PATH)
        r = requests.post(f"{API}/chat/image", json={"text": "你看这个", "image": img_b64}, timeout=90).json()
        ok = bool(r.get("reply")) and r.get("emotion") in ["日常", "调情", "撒娇", "焦急", "冷淡"]
        record("B3", "POST /chat/image 图片对话", ok,
               f"emotion={r.get('emotion')} sticker={r.get('sticker','-')} reply={r.get('reply','')[:40]!r}")
    except Exception as e:
        record("B3", "POST /chat/image 图片对话", False, str(e))

    # B4 /video/frame 视频帧对话
    try:
        img_b64 = load_img_b64(IMG_PATH)
        r = requests.post(f"{API}/video/frame", json={"text": "你看到啥了", "image": img_b64}, timeout=90).json()
        ok = bool(r.get("reply")) and r.get("emotion") in ["日常", "调情", "撒娇", "焦急", "冷淡"]
        record("B4", "POST /video/frame 视频帧对话", ok,
               f"emotion={r.get('emotion')} reply={r.get('reply','')[:40]!r}")
    except Exception as e:
        record("B4", "POST /video/frame 视频帧对话", False, str(e))

    # B5 /tts
    try:
        r = requests.get(f"{API}/tts", params={"text": "你好呀宝贝"}, timeout=60)
        ct = r.headers.get("content-type", "")
        ok = r.status_code == 200 and len(r.content) > 1000 and "audio" in ct
        # 验证是合法 WAV
        is_wav = r.content[:4] == b"RIFF" and r.content[8:12] == b"WAVE"
        record("B5", "GET /tts", ok and is_wav,
               f"{len(r.content)} bytes ct={ct} wav={is_wav}")
    except Exception as e:
        record("B5", "GET /tts", False, str(e))

    # B6 /asr 代理
    try:
        audio_b64 = load_wav_b64(WAV_PATH)
        r = requests.post(f"{API}/asr", json={"audio": audio_b64, "sample_rate": 32000}, timeout=30).json()
        ok = r.status_code == 200 if isinstance(r, dict) and "status_code" in r else bool(r.get("text"))
        record("B6", "POST /asr 代理", bool(r.get("text")), f"text={r.get('text','')[:40]!r}")
    except Exception as e:
        record("B6", "POST /asr 代理", False, str(e))

    # B7 /stickers 静态资源（5 种情绪各取一个）
    try:
        emotions = ["冷淡", "撒娇", "日常", "焦急", "调情"]
        all_ok = True
        for emo in emotions:
            r = requests.get(f"{API}/stickers/{emo}/{emo}.png", timeout=10)
            if r.status_code != 200 or len(r.content) < 100:
                all_ok = False
                record("B7", f"GET /stickers/{emo}/{emo}.png", False, f"{r.status_code} {len(r.content)}b")
                break
        if all_ok:
            record("B7", "GET /stickers（5 情绪）", True, "5/5 全 200")
    except Exception as e:
        record("B7", "GET /stickers", False, str(e))

    # B8 /history
    try:
        r = requests.get(f"{API}/history", params={"limit": 5}, timeout=10).json()
        ok = isinstance(r, list)
        record("B8", "GET /history", ok, f"返回 {len(r)} 条" + (f" 最新role={r[-1].get('role')}" if r else ""))
    except Exception as e:
        record("B8", "GET /history", False, str(e))

    # B9 /reset（放最后，会清历史）
    try:
        r = requests.post(f"{API}/reset", timeout=10).json()
        ok = r.get("ok") is True
        # 验证确实清了
        h = requests.get(f"{API}/history", params={"limit": 5}, timeout=10).json()
        ok = ok and isinstance(h, list) and len(h) == 0
        record("B9", "POST /reset", ok, f"reset={r} history清空={len(h)==0}")
    except Exception as e:
        record("B9", "POST /reset", False, str(e))


# ============================================================
# C. WS 通话测试
# ============================================================
async def test_C():
    section("C. WS 通话测试 (ws_server :8766)")

    # C1 WS 连接 + start/ready 握手
    try:
        async with websockets.connect(f"{WS}/ws/voice", open_timeout=10) as ws:
            await ws.send(json.dumps({"type": "start", "sample_rate": 16000}))
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            d = json.loads(msg)
            ok = d.get("type") == "ready"
            record("C1", "WS 连接 + start/ready 握手", ok, f"收到 {msg}")
    except Exception as e:
        record("C1", "WS 连接 + start/ready 握手", False, str(e))

    # C2 语音通话全链路
    try:
        result = await ws_full_turn(WAV_PATH, with_frame=False)
        ok = (result["asr"] and len(result["llm"]) > 0
              and result["tts_count"] > 0 and result["tts_bytes"] > 1000
              and result["done"])
        record("C2", "语音通话全链路 ASR→LLM→TTS", ok,
               f"asr={result['asr'][:25]!r} llm={len(result['llm'])}句 tts={result['tts_count']}句/{result['tts_bytes']}b done={result['done']}")
    except Exception as e:
        record("C2", "语音通话全链路 ASR→LLM→TTS", False, str(e))

    # C3 打断 abort
    try:
        async with websockets.connect(f"{WS}/ws/voice", open_timeout=10, max_size=10*1024*1024) as ws:
            await ws.send(json.dumps({"type": "start", "sample_rate": 32000}))
            await asyncio.wait_for(ws.recv(), timeout=5)  # ready
            with open(WAV_PATH, "rb") as f:
                wav = f.read()
            for i in range(0, len(wav), 8192):
                await ws.send(wav[i:i+8192])
            await ws.send(json.dumps({"type": "stop", "sample_rate": 32000}))
            # 收到第一个 tts 音频后立即 abort
            got_tts = False
            aborted = False
            try:
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=30)
                    if isinstance(msg, bytes):
                        if not got_tts:
                            got_tts = True
                            await ws.send(json.dumps({"type": "abort"}))
                            aborted = True
                    else:
                        d = json.loads(msg)
                        if d.get("type") == "done":
                            break
            except asyncio.TimeoutError:
                pass
            record("C3", "打断 abort", got_tts and aborted,
                   f"收到TTS={got_tts} 发abort={aborted}")
    except Exception as e:
        record("C3", "打断 abort", False, str(e))

    # C4 视频帧注入 video_frame
    try:
        result = await ws_full_turn(WAV_PATH, with_frame=True)
        # video_frame 注入后，LLM 回复可能提到看到的内容；验证全链路不崩即可
        ok = result["asr"] and result["done"]
        record("C4", "视频帧注入 video_frame", ok,
               f"asr={result['asr'][:25]!r} llm={len(result['llm'])}句 done={result['done']}")
    except Exception as e:
        record("C4", "视频帧注入 video_frame", False, str(e))

    # C5 HTTP /asr 直连 ws_server
    try:
        audio_b64 = load_wav_b64(WAV_PATH)
        r = requests.post(f"{WS_DIRECT_ASR}/asr", json={"audio": audio_b64, "sample_rate": 32000}, timeout=30).json()
        ok = bool(r.get("text"))
        record("C5", "HTTP /asr 直连 ws_server", ok, f"text={r.get('text','')[:40]!r}")
    except Exception as e:
        record("C5", "HTTP /asr 直连 ws_server", False, str(e))


async def ws_full_turn(wav_path: str, with_frame: bool = False) -> dict:
    """跑一轮完整 WS 通话，返回 asr/llm/tts 统计。"""
    async with websockets.connect(f"{WS}/ws/voice", open_timeout=10, max_size=10*1024*1024) as ws:
        await ws.send(json.dumps({"type": "start", "sample_rate": 32000}))
        await asyncio.wait_for(ws.recv(), timeout=5)  # ready
        # 可选：发视频帧
        if with_frame:
            img_b64 = load_img_b64(IMG_PATH)
            await ws.send(json.dumps({"type": "video_frame", "image": img_b64}))
        # 发音频
        with open(wav_path, "rb") as f:
            wav = f.read()
        for i in range(0, len(wav), 8192):
            await ws.send(wav[i:i+8192])
        await ws.send(json.dumps({"type": "stop", "sample_rate": 32000}))
        # 收响应
        asr_text = ""
        llm_chunks = []
        tts_count = 0
        tts_bytes = 0
        done = False
        try:
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=120)
                if isinstance(msg, bytes):
                    tts_count += 1
                    tts_bytes += len(msg)
                else:
                    d = json.loads(msg)
                    t = d.get("type")
                    if t == "asr_text":
                        asr_text = d["text"]
                    elif t == "llm_chunk":
                        llm_chunks.append(d["text"])
                    elif t == "done":
                        done = True
                        break
        except asyncio.TimeoutError:
            pass
        return {"asr": asr_text, "llm": llm_chunks, "tts_count": tts_count,
                "tts_bytes": tts_bytes, "done": done}


# ============================================================
# D. 端到端场景闭环
# ============================================================
def test_D():
    section("D. 端到端场景闭环")

    # D1 文字对话闭环：文本→reply→emotion→TTS
    try:
        r = requests.post(f"{API}/chat", json={"text": "宝贝你在干嘛"}, timeout=60).json()
        reply = r.get("reply", "")
        emotion = r.get("emotion")
        # 取 TTS
        r2 = requests.get(f"{API}/tts", params={"text": reply[:50]}, timeout=60)
        ok = bool(reply) and emotion in ["日常", "调情", "撒娇", "焦急", "冷淡"] and r2.status_code == 200 and len(r2.content) > 1000
        record("D1", "文字对话闭环（chat→emotion→tts）", ok,
               f"emotion={emotion} reply={reply[:30]!r} tts={len(r2.content)}b")
    except Exception as e:
        record("D1", "文字对话闭环", False, str(e))

    # D2 按住说话闭环：录音→/asr→文字→/chat→reply→TTS
    try:
        audio_b64 = load_wav_b64(WAV_PATH)
        r1 = requests.post(f"{API}/asr", json={"audio": audio_b64, "sample_rate": 32000}, timeout=30).json()
        asr_text = r1.get("text", "")
        r2 = requests.post(f"{API}/chat", json={"text": asr_text}, timeout=60).json()
        reply = r2.get("reply", "")
        r3 = requests.get(f"{API}/tts", params={"text": reply[:50]}, timeout=60)
        ok = bool(asr_text) and bool(reply) and r3.status_code == 200
        record("D2", "按住说话闭环（asr→chat→tts）", ok,
               f"asr={asr_text[:20]!r} reply={reply[:20]!r} tts={len(r3.content)}b")
    except Exception as e:
        record("D2", "按住说话闭环", False, str(e))

    # D3 语音通话多轮（两轮 WS）
    try:
        async def multi_round():
            async with websockets.connect(f"{WS}/ws/voice", open_timeout=10, max_size=10*1024*1024) as ws:
                await ws.send(json.dumps({"type": "start", "sample_rate": 32000}))
                await asyncio.wait_for(ws.recv(), timeout=5)
                rounds = []
                for rnd in range(2):
                    if rnd > 0:
                        await ws.send(json.dumps({"type": "start", "sample_rate": 32000}))
                        await asyncio.wait_for(ws.recv(), timeout=5)  # ready
                    with open(WAV_PATH, "rb") as f:
                        wav = f.read()
                    for i in range(0, len(wav), 8192):
                        await ws.send(wav[i:i+8192])
                    await ws.send(json.dumps({"type": "stop", "sample_rate": 32000}))
                    asr = ""
                    done = False
                    try:
                        while True:
                            msg = await asyncio.wait_for(ws.recv(), timeout=120)
                            if isinstance(msg, bytes):
                                continue
                            d = json.loads(msg)
                            if d.get("type") == "asr_text":
                                asr = d["text"]
                            elif d.get("type") == "done":
                                done = True
                                break
                    except asyncio.TimeoutError:
                        pass
                    rounds.append((asr, done))
                return rounds
        rounds = asyncio.run(multi_round())
        ok = all(asr and done for asr, done in rounds)
        record("D3", "语音通话多轮（2 轮）", ok,
               f"r1 asr={rounds[0][0][:15]!r} done={rounds[0][1]} | r2 asr={rounds[1][0][:15]!r} done={rounds[1][1]}")
    except Exception as e:
        record("D3", "语音通话多轮", False, str(e))

    # D4 图片对话闭环：选图→/chat/image→VLM→reply+sticker→表情包可访问
    try:
        img_b64 = load_img_b64(IMG_PATH)
        r = requests.post(f"{API}/chat/image", json={"text": "你看这个", "image": img_b64}, timeout=90).json()
        reply = r.get("reply", "")
        sticker = r.get("sticker", "")
        sticker_ok = True
        if sticker:
            rs = requests.get(f"{API}{sticker}", timeout=10)
            sticker_ok = rs.status_code == 200 and len(rs.content) > 100
        ok = bool(reply) and sticker_ok
        record("D4", "图片对话闭环（chat/image→sticker→可访问）", ok,
               f"reply={reply[:30]!r} sticker={sticker} 可访问={sticker_ok}")
    except Exception as e:
        record("D4", "图片对话闭环", False, str(e))

    # D5 情绪覆盖：跑多次不同输入，收集出现的 emotion 种类
    try:
        prompts = ["在吗", "我想你了求你理理我嘛", "你干嘛呢这么久不回我", "哦随便你吧", "宝贝你好甜"]
        emotions_seen = set()
        for p in prompts:
            r = requests.post(f"{API}/chat", json={"text": p}, timeout=60).json()
            emo = r.get("emotion")
            if emo:
                emotions_seen.add(emo)
        all_5 = set(["日常", "调情", "撒娇", "焦急", "冷淡"])
        # 不强求 5 种全出（LLM 有随机性），>=2 种即通过
        ok = len(emotions_seen) >= 2
        record("D5", f"情绪覆盖（{len(emotions_seen)}/5 种出现）", ok,
               f"出现: {emotions_seen} 缺: {all_5 - emotions_seen}")
    except Exception as e:
        record("D5", "情绪覆盖", False, str(e))


# ============================================================
# E. 异常与边界
# ============================================================
def test_E():
    section("E. 异常与边界")

    # E1 空音频 → /asr
    try:
        # 造一个空 WAV（只有头）
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(b"")
        empty_b64 = base64.b64encode(buf.getvalue()).decode()
        r = requests.post(f"{API}/asr", json={"audio": empty_b64, "sample_rate": 16000}, timeout=30)
        # 不崩 + 200 即可（text 可空）
        ok = r.status_code == 200
        record("E1", "空音频 → /asr", ok, f"status={r.status_code} body={r.text[:60]}")
    except Exception as e:
        record("E1", "空音频 → /asr", False, str(e))

    # E2 超短音频（0.1s 静音）
    try:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(b"\x00\x00" * 1600)  # 0.1s 静音
        short_b64 = base64.b64encode(buf.getvalue()).decode()
        r = requests.post(f"{API}/asr", json={"audio": short_b64, "sample_rate": 16000}, timeout=30)
        ok = r.status_code == 200
        record("E2", "超短静音频 → /asr", ok, f"status={r.status_code} text={r.json().get('text','')!r}")
    except Exception as e:
        record("E2", "超短静音频 → /asr", False, str(e))

    # E3 空文本 → /chat
    try:
        r = requests.post(f"{API}/chat", json={"text": ""}, timeout=60)
        # 不崩即通过（可能 200 或 4xx，但不能 500）
        ok = r.status_code < 500
        record("E3", "空文本 → /chat", ok, f"status={r.status_code} body={r.text[:60]}")
    except Exception as e:
        record("E3", "空文本 → /chat", False, str(e))

    # E4 无效图片 base64 → /chat/image
    try:
        r = requests.post(f"{API}/chat/image", json={"text": "看这个", "image": "不是合法base64图片!!!"}, timeout=90)
        ok = r.status_code < 500
        record("E4", "无效图片 → /chat/image", ok, f"status={r.status_code} body={r.text[:80]}")
    except Exception as e:
        record("E4", "无效图片 → /chat/image", False, str(e))

    # E5 WS 发 stop 无音频
    try:
        async def ws_empty_stop():
            async with websockets.connect(f"{WS}/ws/voice", open_timeout=10) as ws:
                await ws.send(json.dumps({"type": "start", "sample_rate": 16000}))
                await asyncio.wait_for(ws.recv(), timeout=5)  # ready
                await ws.send(json.dumps({"type": "stop", "sample_rate": 16000}))
                msg = await asyncio.wait_for(ws.recv(), timeout=10)
                return msg
        msg = asyncio.run(ws_empty_stop())
        d = json.loads(msg)
        ok = d.get("type") == "done" and d.get("reason") == "empty_audio"
        record("E5", "WS stop 无音频", ok, f"收到 {msg}")
    except Exception as e:
        record("E5", "WS stop 无音频", False, str(e))

    # E6 WS 连接后立即断开（服务端不崩）
    try:
        async def ws_quick_close():
            async with websockets.connect(f"{WS}/ws/voice", open_timeout=10) as ws:
                await ws.send(json.dumps({"type": "start", "sample_rate": 16000}))
                await asyncio.wait_for(ws.recv(), timeout=5)
                # 立即关
            # 等一下让服务端处理断开
            await asyncio.sleep(1)
        asyncio.run(ws_quick_close())
        # 服务端没崩 = 再连一次能成
        async def ws_reconnect():
            async with websockets.connect(f"{WS}/ws/voice", open_timeout=10) as ws:
                await ws.send(json.dumps({"type": "start", "sample_rate": 16000}))
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                return msg
        msg = asyncio.run(ws_reconnect())
        ok = json.loads(msg).get("type") == "ready"
        record("E6", "WS 连接后立即断开（服务端不崩）", ok, "断开后重连成功")
    except Exception as e:
        record("E6", "WS 连接后立即断开", False, str(e))


# ============================================================
# F. 前端契约一致性
# ============================================================
def test_F():
    section("F. 前端契约一致性")

    # F1 pnpm build
    try:
        import subprocess
        webview = os.path.join(HERE, "..", "webview")
        r = subprocess.run(["pnpm", "build"], cwd=webview, capture_output=True, text=True, timeout=120, shell=True)
        ok = r.returncode == 0
        # 提取构建产物行
        last_lines = [l for l in r.stdout.splitlines() if "built in" in l or "error" in l.lower()]
        detail = last_lines[-1] if last_lines else f"exit={r.returncode}"
        record("F1", "pnpm build 编译", ok, detail)
    except Exception as e:
        record("F1", "pnpm build 编译", False, str(e))

    # F2 前后端字段契约核对（静态检查 api/backend.ts vs 后端实际响应）
    try:
        ts_path = os.path.join(HERE, "..", "webview", "src", "api", "backend.ts")
        with open(ts_path, "r", encoding="utf-8") as f:
            ts = f.read()
        # 核对关键契约
        checks = {
            "/chat → {reply, emotion}": "ChatResponse" in ts and "reply" in ts and "emotion" in ts,
            "/chat/image → {reply, emotion, sticker}": "ChatImageResponse" in ts and "sticker" in ts,
            "/asr → {text}": "function asr" in ts and "{ text: string }" in ts,
            "VoiceCallClient 类": "class VoiceCallClient" in ts,
            "WS 路径 /ws/voice": "/ws/voice" in ts,
            "回调 onAsrText/onLlmChunk/onEmotion/onTtsAudio/onDone": all(
                f"on{x}" in ts for x in ["AsrText", "LlmChunk", "Emotion", "TtsAudio", "Done"]),
            "sendAudio/sendVideoFrame/stop/abort 方法": all(
                m in ts for m in ["sendAudio", "sendVideoFrame", "stop(sampleRate", "abort()"]),
        }
        all_ok = all(checks.values())
        detail = "; ".join(f"{k}={'✓' if v else '✗'}" for k, v in checks.items())
        record("F2", "前端契约一致性", all_ok, detail)
    except Exception as e:
        record("F2", "前端契约一致性", False, str(e))


# ============================================================
# 主入口
# ============================================================
def main():
    print("╔" + "═" * 62 + "╗")
    print("║  刘嘉玲 AI 伴侣 — 全流程闭环测试                           ║")
    print("╚" + "═" * 62 + "╝")
    print(f"音频素材: {wav_info(WAV_PATH)}")
    print(f"图片素材: {IMG_PATH}")

    t0 = time.time()

    test_A()
    test_B()
    asyncio.run(test_C())
    test_D()
    test_E()
    test_F()

    elapsed = time.time() - t0
    total = len(results)
    passed = sum(1 for _, _, ok, _ in results if ok)
    failed = total - passed

    print("\n" + "█" * 64)
    print(f"  测试汇总: {passed}/{total} 通过, {failed} 失败, 耗时 {elapsed:.1f}s")
    print("█" * 64)
    if failed:
        print("\n失败用例:")
        for tid, name, ok, detail in results:
            if not ok:
                print(f"  ❌ [{tid}] {name}  — {detail}")
    print()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
