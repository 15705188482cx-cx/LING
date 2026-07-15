# -*- coding: utf-8 -*-
"""表情包库管理：按情绪选表情包，供刘嘉玲主动发表情包。

表情包按 5 情绪分目录存放：
  stickers/日常/  stickers/调情/  stickers/撒娇/  stickers/焦急/  stickers/冷淡/
每个目录放若干 GIF/PNG。无表情包时返回空（前端不显示）。

前端拿到 url（如 /stickers/撒娇/猫猫.gif）直接 <img> 显示。
"""
import logging
import random
from pathlib import Path

import config

logger = logging.getLogger(__name__)

STICKERS_DIR = Path(__file__).resolve().parent / "stickers"


def pick_sticker(emotion: str) -> str:
    """按情绪随机选一个表情包，返回相对 URL 路径（如 /stickers/撒娇/猫猫.gif）。

    没有表情包（目录空或不存在）返回空字符串，前端不显示。
    emotion 非法则回退到"日常"。
    """
    if emotion not in config.EMOTIONS:
        emotion = "日常"

    emo_dir = STICKERS_DIR / emotion
    if not emo_dir.exists():
        return ""

    # 支持的图片格式
    exts = {".gif", ".png", ".jpg", ".jpeg", ".webp"}
    files = [f for f in emo_dir.iterdir() if f.suffix.lower() in exts]
    if not files:
        return ""

    chosen = random.choice(files)
    # 返回 URL 路径（api_server mount /stickers 到 stickers/ 目录）
    return f"/stickers/{emotion}/{chosen.name}"


def has_stickers(emotion: str) -> bool:
    """某情绪是否有表情包可用。"""
    if emotion not in config.EMOTIONS:
        emotion = "日常"
    emo_dir = STICKERS_DIR / emotion
    if not emo_dir.exists():
        return False
    exts = {".gif", ".png", ".jpg", ".jpeg", ".webp"}
    return any(f.suffix.lower() in exts for f in emo_dir.iterdir())
