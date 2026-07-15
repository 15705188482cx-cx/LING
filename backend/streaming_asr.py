# -*- coding: utf-8 -*-
"""流式 ASR：sherpa-onnx OnlineRecognizer，边说边出文字。

【验证结论 2026-07-14】已实测，暂未启用。
sherpa-onnx 流式 ASR 速度极快（48-109ms vs FunASR 400ms，省 ~300ms），
但准确率明显低于 FunASR SenseVoiceSmall——三段测试音频 sherpa 识别均不准确
（如"哎今天嘴这么甜你说不哈哈哈" sherpa 识别成"啊今天嘴子里这东西填你是不好"）。
陪伴对话场景识别错会导致 LLM 回复跑偏，准确率优先于 300ms 延迟。
故 ling 仍用 FunASR 整段识别。本模块保留待后续模型升级（更大流式模型）后启用。

模型：sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23（int8，~25MB，纯中文流式）
下载：https://github.com/k2-fsa/sherpa-onnx/releases
通过环境变量 STREAMING_ASR_MODEL_DIR 指定模型目录。
"""
import logging
import os
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 流式 zipformer 中文 14M 模型（int8 量化，CPU 友好），通过 env 配置
_STREAMING_MODEL_DIR = Path(
    os.environ.get(
        "STREAMING_ASR_MODEL_DIR",
        "",
    )
)

# 端点检测参数
# rule1 = 开说前静音上限：ling 有独立 SileroVAD 判断有声/无声，sherpa 只收有声段，
#         故 rule1 设极大值禁用（避免开头短停顿被误判端点重置流）
# rule2 = 说话中静音上限：兜底端点（主端点信号由 ling VAD 提供，这里仅防卡死）
_RULE1_SILENCE_SEC = 100.0  # 实际禁用
_ENDPOINT_SILENCE_SEC = 0.6  # rule2，对齐 config.VAD_SILENCE_MS

# 单句最大时长（秒），超时强制端点，防卡死
_MAX_UTTERANCE_SEC = 20.0


class StreamingASR:
    """sherpa-onnx 流式 ASR 单例。每条 WS 连接用 new_stream() 建独立流。"""

    def __init__(self):
        self.enabled = False
        self._recognizer = None
        try:
            import sherpa_onnx

            enc = _STREAMING_MODEL_DIR / "encoder-epoch-99-avg-1.int8.onnx"
            dec = _STREAMING_MODEL_DIR / "decoder-epoch-99-avg-1.int8.onnx"
            jnr = _STREAMING_MODEL_DIR / "joiner-epoch-99-avg-1.int8.onnx"
            tok = _STREAMING_MODEL_DIR / "tokens.txt"

            missing = [p for p in (enc, dec, jnr, tok) if not p.exists()]
            if missing:
                logger.error(
                    f"[StreamingASR] 模型文件缺失: {[str(p) for p in missing]}，"
                    f"流式 ASR 不可用（回退 FunASR 整段识别）"
                )
                return

            self._recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
                tokens=str(tok),
                encoder=str(enc),
                decoder=str(dec),
                joiner=str(jnr),
                num_threads=2,
                sample_rate=16000,
                feature_dim=80,
                model_type="zipformer",
                enable_endpoint_detection=True,
                rule1_min_trailing_silence=_RULE1_SILENCE_SEC,
                rule2_min_trailing_silence=_ENDPOINT_SILENCE_SEC,
                rule3_min_utterance_length=_MAX_UTTERANCE_SEC,
                decoding_method="greedy_search",
                provider="cpu",
            )
            self.enabled = True
            logger.info(
                f"[StreamingASR] 模型加载完成: zh-14M int8, "
                f"endpoint_silence={_ENDPOINT_SILENCE_SEC}s"
            )
        except Exception as e:
            logger.error(f"[StreamingASR] 加载失败，回退 FunASR: {e}")
            self.enabled = False

    def new_stream(self) -> Optional["StreamingStream"]:
        """新建一条流式识别流（每条 WS 连接 / 每轮调用一次）。"""
        if not self.enabled or self._recognizer is None:
            return None
        try:
            return StreamingStream(self._recognizer)
        except Exception as e:
            logger.error(f"[StreamingASR] 建流失败: {e}")
            return None


class StreamingStream:
    """单条流式识别流。封装 sherpa OnlineStream 的喂帧/解码/端点/取文/重置。

    线程安全：喂帧和解码都在 ws_server 的 VAD 回调线程里串行调用，
    但显式加锁防御前端快速连发 Opus 包时的竞态。
    """

    def __init__(self, recognizer):
        self._rec = recognizer
        self._stream = recognizer.create_stream()
        self._lock = threading.Lock()
        self._final_text = ""

    def feed(self, pcm_int16_bytes: bytes, sample_rate: int = 16000) -> tuple[str, bool]:
        """喂一帧 PCM（int16 bytes），返回 (partial_text, is_endpoint)。

        Args:
            pcm_int16_bytes: Opus 解码后的 PCM，int16 单声道，通常 60ms/960 样本。
            sample_rate: 采样率，sherpa 要求 16000。
        Returns:
            partial_text: 当前累计识别文本（边说边出字）
            is_endpoint: True=端点到达（说完），此时 partial_text 即最终文本
        """
        if not pcm_int16_bytes:
            return self._final_text, False
        try:
            import numpy as np

            # int16 bytes → float32 [-1,1]（sherpa 要求归一化）
            samples = np.frombuffer(pcm_int16_bytes, dtype=np.int16).astype(np.float32) / 32768.0

            with self._lock:
                self._stream.accept_waveform(sample_rate, samples)
                # 尽量多解码（一帧可能触发多次 decode）
                while self._recognizer_is_ready():
                    self._rec.decode_stream(self._stream)

                partial = self._rec.get_result(self._stream) or ""
                endpoint = self._rec.is_endpoint(self._stream)

                if endpoint:
                    # 端点：锁定最终文本，重置流开始下一句
                    self._final_text = partial.strip()
                    self._rec.reset(self._stream)
                    return self._final_text, True
                return partial.strip(), False
        except Exception as e:
            logger.error(f"[StreamingStream] feed 失败: {e}")
            return self._final_text, False

    def finalize(self) -> str:
        """取最终文本（端点后或强制结束时调用）。"""
        with self._lock:
            if self._final_text:
                return self._final_text
            text = (self._rec.get_result(self._stream) or "").strip()
            self._final_text = text
            return text

    def reset(self) -> None:
        """重置流（打断后或开始新一轮时调用）。"""
        with self._lock:
            self._final_text = ""
            self._rec.reset(self._stream)

    def _recognizer_is_ready(self) -> bool:
        """封装 is_ready 调用（lock 内）。"""
        return self._rec.is_ready(self._stream)
