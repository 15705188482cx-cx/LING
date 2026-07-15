# -*- coding: utf-8 -*-
"""TTS 短回复缓存 —— 命中时跳过 TTS 合成 + Opus 编码，0ms 出包。

通话场景下，LLM 首句常是短语气词（"在呢"、"嗯嗯"、"哈哈"、"讨厌啦"），
每次都调 GPT-SoVITS 合成 ~600ms 太慢。这里预合成并缓存 Opus 编码后的包列表，
命中时直接返回，省 600ms TTS + 3ms 编码。

缓存粒度：整句文本（strip 后）精确匹配。不缓存长句（>12 字命中率低且占内存）。
TTL 1 小时（运行时也缓存动态命中的短句，避免重复合成）。
"""
import logging
import threading
import time
from typing import Optional

from opus_codec import OpusEncoder

logger = logging.getLogger(__name__)

# 缓存上限：最多缓存 200 条短回复的 Opus 包
_MAX_ENTRIES = 200
_MAX_TEXT_LEN = 12  # 超过此长度的文本不缓存（命中率低）
_TTL_SEC = 3600  # 1 小时

_lock = threading.Lock()
# text → {"packets": [bytes,...], "ts": float}
_cache: dict[str, dict] = {}

# 预热用的高频短回复（首次请求时懒加载合成）
_WARMUP_TEXTS = [
    "在呢", "嗯嗯", "哈哈", "嘿嘿", "讨厌啦", "哼", "好吧", "知道了",
    "哦", "嗯", "才不要", "你说呢", "怎么了", "干嘛", "没事",
]


def get(text: str) -> Optional[list[bytes]]:
    """查缓存。命中返回 Opus 包列表（深拷贝避免被消费），未命中返回 None。"""
    key = text.strip()
    if len(key) > _MAX_TEXT_LEN:
        return None
    now = time.time()
    with _lock:
        entry = _cache.get(key)
        if not entry:
            return None
        if now - entry["ts"] > _TTL_SEC:
            del _cache[key]
            return None
        # 返回拷贝（调用方会逐个 send，不希望原数据被改）
        return list(entry["packets"])
    return None


def put(text: str, opus_packets: list[bytes]) -> None:
    """缓存一条短回复的 Opus 包。超长/空不缓存。"""
    key = text.strip()
    if not key or len(key) > _MAX_TEXT_LEN or not opus_packets:
        return
    now = time.time()
    with _lock:
        # 淘汰最老的
        if len(_cache) >= _MAX_ENTRIES:
            oldest = min(_cache, key=lambda k: _cache[k]["ts"])
            del _cache[oldest]
        _cache[key] = {"packets": list(opus_packets), "ts": now}


def encode_and_cache(text: str, wav_bytes: bytes) -> list[bytes]:
    """WAV → PCM → Opus 编码，短回复顺带缓存。返回 Opus 包列表。"""
    from opus_codec import wav_bytes_to_pcm

    pcm = wav_bytes_to_pcm(wav_bytes)
    if not pcm:
        return []

    encoder = OpusEncoder()
    packets: list[bytes] = []
    encoder.encode(pcm, callback=packets.append, end_of_stream=True)
    encoder.reset()

    # 短回复缓存
    put(text, packets)
    return packets


def warmup(synthesize_fn) -> None:
    """预热：用传入的合成函数预合成高频短回复。启动时调一次。

    synthesize_fn: async fn(text) -> wav_bytes，调 tts_server。
    失败静默（tts 没起时不阻塞启动）。
    """
    import asyncio

    async def _do():
        for text in _WARMUP_TEXTS:
            if get(text):
                continue  # 已缓存
            try:
                wav = await synthesize_fn(text)
                encode_and_cache(text, wav)
            except Exception as e:
                logger.debug(f"预热 '{text}' 失败: {e}")
                break  # tts 没起，后面的也会失败，跳过
        logger.info(f"TTS 缓存预热完成（{len(_cache)} 条）")

    try:
        loop = asyncio.get_event_loop()
        loop.create_task(_do())
    except Exception:
        pass  # 没有事件循环（import 时），跳过


def stats() -> dict:
    """缓存统计（调试用）。"""
    with _lock:
        return {"entries": len(_cache), "max": _MAX_ENTRIES}
