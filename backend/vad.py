# -*- coding: utf-8 -*-
"""SileroVAD 语音活动检测 —— onnxruntime 路线（不依赖 torch 推理）。

适配成 ling 的单例模式：
- VAD 类启动时加载一次 ONNX 模型（CPU 单线程，低且可预测的延迟）
- 每条 WS 连接用独立 session_state dict 隔离状态（_vad_state/_vad_context/窗口等）
- is_vad(pcm_bytes, state) 逐 512 样本块（32ms）判定，双阈值滞回 + 3 帧滑窗去抖
- detect_endpoint(state) 判断「有声→无声超 VAD_SILENCE_MS」→ 说完了

VAD 只在 auto 模式生效；manual 模式（按住说话）前端发 start/stop，不经过 VAD。
模型来自 silero-vad pip 包（pip install silero-vad），缺失时自动降级。
"""
import logging
import os
import time
from collections import deque
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


def _find_vad_model() -> Optional[str]:
    """定位 silero_vad.onnx 模型文件。

    优先级：VAD_MODEL_PATH 环境变量 > silero_vad 包自带 > 本地 assets 目录。
    找不到返回 None（调用方降级处理）。
    """
    # 1. 环境变量显式指定
    env_path = os.environ.get("VAD_MODEL_PATH", "")
    if env_path and Path(env_path).exists():
        return env_path

    # 2. silero_vad pip 包自带
    try:
        import silero_vad as _svad
        pkg_dir = Path(_svad.__file__).resolve().parent
        cand = pkg_dir / "data" / "silero_vad.onnx"
        if cand.exists():
            return str(cand)
    except ImportError:
        pass

    # 3. backend/assets 目录兜底
    cand = Path(__file__).resolve().parent / "assets" / "silero_vad.onnx"
    if cand.exists():
        return str(cand)

    return None


_VAD_MODEL_PATH = _find_vad_model()

# VAD 常量（与 silero_vad 模型要求一致，勿改）
_VAD_SAMPLE_RATE = 16000
_VAD_CHUNK_SAMPLES = 512  # 512 样本 = 32ms @16kHz
_VAD_CONTEXT_SAMPLES = 64  # 模型要求的前置上下文


class VAD:
    """SileroVAD 单例。启动时加载模型，之后每条连接用独立 state 调 is_vad。"""

    def __init__(
        self,
        threshold: float = 0.5,
        threshold_low: float = 0.2,
        silence_ms: int = 800,
    ):
        self.threshold = threshold
        self.threshold_low = threshold_low
        self.silence_ms = silence_ms
        self.frame_window = 3  # 连续 3 帧有声才算「有声音」

        if _VAD_MODEL_PATH is None:
            logger.warning(
                "[VAD] 未找到 silero_vad.onnx（pip install silero-vad 或设 VAD_MODEL_PATH），"
                "语音通话自动断句将不可用"
            )
            self.session = None
            self.enabled = False
            return

        try:
            import onnxruntime
            opts = onnxruntime.SessionOptions()
            opts.inter_op_num_threads = 1
            opts.intra_op_num_threads = 1
            self.session = onnxruntime.InferenceSession(
                _VAD_MODEL_PATH,
                providers=["CPUExecutionProvider"],
                sess_options=opts,
            )
            self.enabled = True
            logger.info(
                f"[VAD] SileroVAD 加载完成 (threshold={threshold}, silence={silence_ms}ms)"
            )
        except Exception as e:
            logger.error(f"[VAD] 加载失败，语音通话自动断句不可用: {e}")
            self.session = None
            self.enabled = False

    def new_state(self) -> dict:
        """为一条 WS 连接创建独立的 VAD 状态。连接建立时调一次。"""
        return {
            "_vad_state": np.zeros((2, 1, 128), dtype=np.float32),
            "_vad_context": np.zeros((1, _VAD_CONTEXT_SAMPLES), dtype=np.float32),
            "_audio_buffer": bytearray(),  # 累积未处理的 PCM 字节
            "last_is_voice": False,
            "voice_window": deque(maxlen=self.frame_window),
            "have_voice": False,  # 本连接是否曾检测到有声（粘性，断句后重置）
            "last_voice_time": 0.0,  # 最后一次有声的时间戳（毫秒）
            "voice_stop": False,  # 端点标志：说完一句话
        }

    def reset_for_new_turn(self, state: dict) -> None:
        """一轮处理完后重置端点相关状态，准备下一轮（保留模型 state/context 连续性）。"""
        state["have_voice"] = False
        state["voice_stop"] = False
        state["last_voice_time"] = 0.0
        state["voice_window"].clear()
        # _audio_buffer 保留尾部少量（避免断句瞬间的尾音丢失），清掉大部分
        if len(state["_audio_buffer"]) > _VAD_CHUNK_SAMPLES * 2 * 5:
            state["_audio_buffer"] = state["_audio_buffer"][-_VAD_CHUNK_SAMPLES * 2 * 5 :]

    def is_vad(self, pcm_bytes: bytes, state: dict) -> bool:
        """喂一段 PCM（int16 16kHz 单声道 bytes），返回当前窗口是否有语音。

        内部按 512 样本块逐块判定，更新 state。同时检测端点：
        有声→无声超 silence_ms → state['voice_stop']=True。
        """
        if not pcm_bytes:
            return False

        # VAD 禁用时（模型缺失），不做端点检测，直接返回 False
        if not self.enabled or self.session is None:
            return False

        state["_audio_buffer"].extend(pcm_bytes)
        window_have_voice = False

        while len(state["_audio_buffer"]) >= _VAD_CHUNK_SAMPLES * 2:
            chunk = state["_audio_buffer"][: _VAD_CHUNK_SAMPLES * 2]
            del state["_audio_buffer"][: _VAD_CHUNK_SAMPLES * 2]

            audio_int16 = np.frombuffer(chunk, dtype=np.int16)
            audio_float32 = audio_int16.astype(np.float32) / 32768.0
            # 拼上 64 样本上下文 → (1, 576)
            audio_input = np.concatenate(
                [state["_vad_context"], audio_float32.reshape(1, -1)], axis=1
            ).astype(np.float32)

            ort_inputs = {
                "input": audio_input,
                "state": state["_vad_state"],
                "sr": np.array(_VAD_SAMPLE_RATE, dtype=np.int64),
            }
            out, new_state = self.session.run(None, ort_inputs)
            state["_vad_state"] = new_state
            state["_vad_context"] = audio_input[:, -_VAD_CONTEXT_SAMPLES:]
            speech_prob = out.item()

            # 双阈值滞回：高阈值确认有声，低阈值确认无声，中间区间延续上一帧
            if speech_prob >= self.threshold:
                is_voice = True
            elif speech_prob <= self.threshold_low:
                is_voice = False
            else:
                is_voice = state["last_is_voice"]
            state["last_is_voice"] = is_voice

            # 滑动窗口去抖：连续 3 帧有声才算「有声音」
            state["voice_window"].append(is_voice)
            window_have_voice = state["voice_window"].count(True) >= self.frame_window

            # 端点检测：之前有声 + 当前无声 + 静音超阈值 → 说完了
            if state["have_voice"] and not window_have_voice:
                if state["last_voice_time"] > 0:
                    stop_duration = time.time() * 1000 - state["last_voice_time"]
                    if stop_duration >= self.silence_ms:
                        state["voice_stop"] = True
            if window_have_voice:
                state["have_voice"] = True
                state["last_voice_time"] = time.time() * 1000

        return window_have_voice

    def detect_endpoint(self, state: dict) -> bool:
        """是否检测到端点（说完一句话）。ws_server 主循环调此判断是否触发 process_turn。"""
        return state["voice_stop"]
