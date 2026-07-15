# -*- coding: utf-8 -*-
"""Opus 编解码封装 —— 双向 Opus，移植自 xiaozhi-server。

- OpusEncoder：有状态流式编码器（16kHz/mono/60ms 帧/24kbps）。
  TTS 的 WAV→PCM→Opus 帧逐包发，状态跨调用保持连续（不能每帧重置）。
- OpusDecoder：每条 WS 连接一个，上行麦克风 Opus 包→PCM（960 样本/帧）。

参数与 xiaozhi 对齐（勿改，前后端 + VAD 帧大小一致）：
  采样率 16000 / 单声道 / 60ms 帧 = 960 样本 / 24kbps / complexity 10
"""
import logging
from typing import Callable, Optional

import numpy as np
from opuslib_next import Encoder, Decoder, constants

logger = logging.getLogger(__name__)

# 全局常量（与 xiaozhi、前端、VAD 保持一致）
OPUS_SAMPLE_RATE = 16000
OPUS_CHANNELS = 1
OPUS_FRAME_MS = 60
OPUS_FRAME_SIZE = OPUS_SAMPLE_RATE * OPUS_FRAME_MS // 1000  # 960 样本
OPUS_BITRATE = 24000  # bps
OPUS_COMPLEXITY = 10


class OpusEncoder:
    """有状态流式 Opus 编码器。一次 TTS 句子期间复用，保持编码器状态连续。

    用法：
        enc = OpusEncoder()
        enc.encode(pcm_bytes, callback=lambda opus_pkt: send(opus_pkt))  # 可多次调
        enc.encode(more_pcm, callback=..., end=True)  # 最后一次 end=True 刷尾
        enc.reset()  # 下一句前重置（清缓冲 + 重置编码器内部状态）
    """

    def __init__(self):
        self.frame_size = OPUS_FRAME_SIZE
        self.total_frame_size = OPUS_FRAME_SIZE * OPUS_CHANNELS
        self.buffer = np.array([], dtype=np.int16)
        self.encoder = Encoder(
            OPUS_SAMPLE_RATE, OPUS_CHANNELS, constants.APPLICATION_AUDIO
        )
        self.encoder.bitrate = OPUS_BITRATE
        self.encoder.complexity = OPUS_COMPLEXITY
        self.encoder.signal = constants.SIGNAL_VOICE

    def encode(
        self,
        pcm_data: bytes,
        callback: Callable[[bytes], None],
        end_of_stream: bool = False,
    ) -> None:
        """将 PCM bytes 编码为 Opus 包，每个包调一次 callback。

        内部维护 numpy 缓冲区，按完整 960 样本帧切片编码；
        end_of_stream=True 时末尾不足一帧的补零编出最后一包。
        """
        if not pcm_data:
            if end_of_stream and len(self.buffer) > 0:
                self._flush_tail(callback)
            return

        new_samples = np.frombuffer(pcm_data, dtype=np.int16)
        self.buffer = np.append(self.buffer, new_samples)

        offset = 0
        while offset <= len(self.buffer) - self.total_frame_size:
            frame = self.buffer[offset : offset + self.total_frame_size]
            pkt = self._encode_frame(frame)
            if pkt:
                callback(pkt)
            offset += self.total_frame_size
        self.buffer = self.buffer[offset:]

        if end_of_stream and len(self.buffer) > 0:
            self._flush_tail(callback)

    def _flush_tail(self, callback: Callable[[bytes], None]) -> None:
        """末尾不足一帧补零编出最后一包。"""
        last = np.zeros(self.total_frame_size, dtype=np.int16)
        last[: len(self.buffer)] = self.buffer
        pkt = self._encode_frame(last)
        if pkt:
            callback(pkt)
        self.buffer = np.array([], dtype=np.int16)

    def _encode_frame(self, frame: np.ndarray) -> Optional[bytes]:
        try:
            return self.encoder.encode(frame.tobytes(), self.frame_size)
        except Exception as e:
            logger.error(f"Opus 编码失败: {e}")
            return None

    def reset(self) -> None:
        """重置编码器（下一句 TTS 前调）。清缓冲 + 重置内部状态。"""
        self.encoder.reset_state()
        self.buffer = np.array([], dtype=np.int16)


class OpusDecoder:
    """Opus 解码器。每条 WS 连接一个，上行麦克风 Opus 包→PCM bytes。

    用法：
        dec = OpusDecoder()
        pcm = dec.decode(opus_packet)  # → 960 样本的 PCM bytes（1920 字节）
    """

    def __init__(self):
        self.frame_size = OPUS_FRAME_SIZE
        self.decoder = Decoder(OPUS_SAMPLE_RATE, OPUS_CHANNELS)

    def decode(self, opus_packet: bytes) -> Optional[bytes]:
        """解码一个 Opus 包为 PCM bytes（960 样本 = 1920 字节）。失败返回 None。"""
        if not opus_packet:
            return None
        try:
            return self.decoder.decode(opus_packet, self.frame_size)
        except Exception as e:
            logger.debug(f"Opus 解码失败: {e}")
            return None


def wav_bytes_to_pcm(wav_bytes: bytes) -> bytes:
    """WAV bytes → PCM bytes（去 44 字节头）。TTS 返回的是 WAV，编码前先剥头。"""
    import wave
    import io

    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as w:
            return w.readframes(w.getnframes())
    except Exception as e:
        logger.error(f"WAV→PCM 失败: {e}")
        return b""
