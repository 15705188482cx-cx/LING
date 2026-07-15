# -*- coding: utf-8 -*-
"""个人资料层（名字/头像/签名）—— ling 自有，存 ling_data.db。

复用 idempotency.py 的模式（同 DB 文件 + 线程锁 + 单连接）。
key-value 结构存 name / signature / avatar（base64 data URL）。

不碰 Create-Ex chat.db；后端 LLM prompt 不读这里（她自称不变，仅前端显示名可改）。
"""
import sqlite3
import threading
from pathlib import Path
from typing import Optional

DB_PATH = str(Path(__file__).resolve().parent / "ling_data.db")

# 默认值：DB 为空或字段缺失时返回
DEFAULTS = {
    "name": "刘嘉玲",
    "signature": "在呢宝贝，怎么了",
    "avatar": "",  # 空 = 前端用默认 svg 头像
}

_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.execute(
            """
            CREATE TABLE IF NOT EXISTS profile (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        _conn.commit()
    return _conn


def get_profile() -> dict:
    """读取 profile，缺失字段补默认值。返回 {name, signature, avatar}。"""
    with _lock:
        cur = _get_conn().execute(
            "SELECT key, value FROM profile WHERE key IN ('name', 'signature', 'avatar')"
        )
        rows = {k: v for k, v in cur.fetchall()}
    return {
        "name": rows.get("name", DEFAULTS["name"]),
        "signature": rows.get("signature", DEFAULTS["signature"]),
        "avatar": rows.get("avatar", DEFAULTS["avatar"]),
    }


def set_profile(name: Optional[str] = None, signature: Optional[str] = None, avatar: Optional[str] = None) -> None:
    """更新 profile，只更新传入的非 None 字段（None=不改动）。"""
    updates = {}
    if name is not None:
        updates["name"] = name
    if signature is not None:
        updates["signature"] = signature
    if avatar is not None:
        updates["avatar"] = avatar
    if not updates:
        return
    with _lock:
        conn = _get_conn()
        for k, v in updates.items():
            conn.execute(
                "INSERT INTO profile (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (k, v),
            )
        conn.commit()
