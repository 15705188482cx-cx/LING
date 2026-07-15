# -*- coding: utf-8 -*-
"""ASR 语音识别封装：FunASR (SenseVoiceSmall 本地模型)。

需在环境变量 ASR_MODEL_DIR 指定 SenseVoiceSmall 模型目录（约 894MB，不入仓库）。
模型来源：https://github.com/FunAudioLLM/SenseVoice
不花钱、不联网、中文识别质量高。
输入：PCM 16kHz 单声道 bytes（浏览器 MediaRecorder 录的 wav 可直接转 PCM）
输出：识别文字（已过滤语言标签）

启动时加载模型（~2-3秒），之后每次 transcribe 调用 ~200-500ms。
模型缺失时自动降级（enabled=False），语音通话不可用但不影响文字聊天。
"""
import logging
import os
import re

logger = logging.getLogger(__name__)

# SenseVoiceSmall 模型目录（env 配置，缺失则禁用 ASR）
MODEL_DIR = os.environ.get("ASR_MODEL_DIR", "")


class ASR:
    """本地 FunASR 语音识别。启动时加载一次，之后复用。"""

    def __init__(self):
        if not MODEL_DIR:
            logger.warning("[ASR] 未配置 ASR_MODEL_DIR，语音识别禁用")
            self.model = None
            self.enabled = False
            return
        try:
            from funasr import AutoModel
            logger.info(f"[ASR] 加载 SenseVoiceSmall 模型: {MODEL_DIR}")
            self.model = AutoModel(
                model=MODEL_DIR,
                vad_kwargs={"max_single_segment_time": 30000},
                disable_update=True,
                hub="hf",
            )
            self.enabled = True
            logger.info("[ASR] 模型加载完成")
        except Exception as e:
            logger.error(f"[ASR] 加载失败，语音通话将不可用: {e}")
            self.model = None
            self.enabled = False

    def transcribe(self, pcm_bytes: bytes, sample_rate: int = 16000) -> str:
        """PCM bytes → 识别文字。

        Args:
            pcm_bytes: PCM 音频数据。若采样率非 16kHz 会自动重采样。
            sample_rate: 输入音频的采样率（FunASR 要求 16kHz）。
        失败返回空字符串。SenseVoiceSmall 输出带 <|zh|> 等语言标签，需过滤。
        """
        if not self.enabled or self.model is None:
            return ""
        try:
            # FunASR 要求 16kHz，非 16kHz 输入需重采样
            if sample_rate != 16000:
                pcm_bytes = self._resample(pcm_bytes, sample_rate, 16000)

            # 静音 funasr 的 tqdm 进度条
            import logging as _logging
            _logging.getLogger("funasr").setLevel(_logging.WARNING)

            result = self.model.generate(
                input=pcm_bytes,
                cache={},
                language="auto",
                use_itn=True,
                batch_size_s=60,
            )
            raw_text = result[0]["text"] if result else ""
            # 过滤 <|zh|><|NEUTRAL|><|Speech|> 等标签
            text = re.sub(r"<\|[^|]+\|>", "", raw_text).strip()
            logger.info(f"[ASR] 识别: {text[:60]}")
            return text
        except Exception as e:
            logger.error(f"[ASR] 识别失败: {e}")
            return ""

    def _resample(self, pcm_bytes: bytes, orig_sr: int, target_sr: int) -> bytes:
        """用 scipy 重采样 PCM 16bit 单声道。"""
        import numpy as np
        import scipy.signal
        audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
        # 归一化到 [-1, 1] 再重采样
        audio = audio / 32768.0
        from math import gcd
        g = gcd(orig_sr, target_sr)
        up, down = target_sr // g, orig_sr // g
        resampled = scipy.signal.resample_poly(audio, up, down)
        # 转回 int16 bytes
        return (resampled * 32768.0).astype(np.int16).tobytes()
