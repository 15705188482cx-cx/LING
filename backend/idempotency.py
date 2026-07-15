# -*- coding: utf-8 -*-
"""client_message_id 幂等去重层（ling 自有，不依赖 Create-Ex chat_db）。

chat_db（Create-Ex 共享层）不可改，没有 client_message_id 列。这里用 ling 自有的
SQLite 文件建一张去重表：同 client_message_id 的 /chat 请求在 TTL 内直接返回缓存结果，
不重调 LLM、不重复 append_message。

设计要点：
- 空 id 直通（不缓存）——兼容不带 id 的旧客户端/测试
- TTL 24h：足够覆盖重试窗口，又不会让表无限膨胀
- 线程安全：SQLite 连接 + threading.Lock（FastAPI 同步路由跑在线程池里）
- 懒过期：get 时查到再比对 created_at，过期返回 None；写入时顺带清理超期行
"""
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

# ling 自有 DB 文件，与 Create-Ex 的 chat.db 完全分开
DB_PATH = str(Path(__file__).resolve().parent / "ling_data.db")
TTL_SECONDS = 24 * 3600

_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.execute(
            """
            CREATE TABLE IF NOT EXISTS idempotency (
                client_message_id TEXT PRIMARY KEY,
                reply TEXT NOT NULL,
                emotion TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        _conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_idem_created ON idempotency(created_at)"
        )
        _conn.commit()
    return _conn


def get(client_message_id: str) -> Optional[dict]:
    """命中返回 {reply, emotion}，未命中/过期/空 id 返回 None。"""
    if not client_message_id:
        return None
    with _lock:
        cur = _get_conn().execute(
            "SELECT reply, emotion, created_at FROM idempotency WHERE client_message_id = ?",
            (client_message_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    reply, emotion, created_at = row
    if time.time() - created_at > TTL_SECONDS:
        return None  # 已过期，调用方会重新处理
    return {"reply": reply, "emotion": emotion}


def put(client_message_id: str, reply: str, emotion: str) -> None:
    """缓存一条结果。空 id 不缓存。重复 put（同 id）按首次为准——INSERT OR IGNORE。"""
    if not client_message_id:
        return
    now = time.time()
    with _lock:
        conn = _get_conn()
        conn.execute(
            "INSERT OR IGNORE INTO idempotency (client_message_id, reply, emotion, created_at) VALUES (?, ?, ?, ?)",
            (client_message_id, reply, emotion, now),
        )
        # 顺带清理超期行（低频写时清理，避免膨胀）
        conn.execute("DELETE FROM idempotency WHERE created_at < ?", (now - TTL_SECONDS,))
        conn.commit()


def clear() -> None:
    """清空去重表（仅测试用）。"""
    with _lock:
        _get_conn().execute("DELETE FROM idempotency")
        _get_conn().commit()
