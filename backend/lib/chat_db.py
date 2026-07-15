# -*- coding: utf-8 -*-
"""SQLite 共享层 - 让 chatbot (Telegram) 和 xiaozhi-server (ESP32) 用同一份对话历史。
放在 shared/ 下，进 git 也不带 db 文件 (.gitignore)。
"""
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import List, Optional

# 默认 db 路径（可被环境变量 DB_PATH 覆盖）
DEFAULT_DB_DIR = Path(__file__).resolve().parent
DB_PATH = Path(
    os.environ.get("DB_PATH", str(DEFAULT_DB_DIR / "chat.db"))
)

# ---------- 表 schema ----------
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE,
    device_id TEXT UNIQUE,
    created_at REAL DEFAULT (strftime('%s','now')),
    last_seen_at REAL DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL,        -- 'system' | 'user' | 'assistant'
    content TEXT NOT NULL,
    channel TEXT NOT NULL,     -- 'telegram' | 'xiaozhi'
    ts REAL DEFAULT (strftime('%s','now')),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_messages_user_ts ON messages(user_id, ts);
"""

# ---------- 线程安全连接 ----------
# 用 RLock（可重入）：get_or_create_user 等函数持锁后还会调 get_conn()，
# get_conn() 内部也会拿锁；threading.Lock 不可重入会死锁，必须用 RLock。
_lock = threading.RLock()
_conn_cache = {}  # thread-local? 我们用全局锁


def _connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = db_path or str(DB_PATH)
    conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")  # 写性能更好，chatbot + 小智 后端并发更安全
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def get_conn() -> sqlite3.Connection:
    """获取全局共享连接（调用方自行用 _lock 包临界区）。"""
    if "_main" not in _conn_cache:
        with _lock:
            if "_main" not in _conn_cache:
                conn = _connect()
                conn.executescript(SCHEMA)
                _conn_cache["_main"] = conn
    return _conn_cache["_main"]


def init_db(db_path: Optional[str] = None) -> None:
    """显式初始化（看 db 文件位置 + 建表）。"""
    with _lock:
        path = db_path or str(DB_PATH)
        conn = _connect(path)
        conn.executescript(SCHEMA)
        conn.commit()
        _conn_cache["_main"] = conn  # 缓存
    print(f"[chat_db] 已初始化: {path}")


# ---------- 用户管理 ----------
def get_or_create_user(
    telegram_id: Optional[int] = None,
    device_id: Optional[str] = None,
) -> int:
    """用 telegram_id 或 device_id 找/创建用户，返回 user_id。

    注意：同一个人可能有 telegram_id 和 device_id 都会被赋给同一 user：
    - 第一次用 telegram 创建 → telegram_id=N, device_id=null
    - 之后这个人在 ESP32 上首次连 → 把 device_id 更新到这个 user 的 row
    """
    if telegram_id is None and device_id is None:
        raise ValueError("telegram_id or device_id 至少传一个")

    with _lock:
        conn = get_conn()

        # Step 1: 找 telegram match（exact match 优先，UNIQUE 列）
        if telegram_id is not None:
            row = conn.execute(
                "SELECT id, device_id FROM users WHERE telegram_id = ?",
                (telegram_id,),
            ).fetchone()
            if row:
                user_id = row["id"]
                # 如果 device_id 不一致需要合并，先迁移
                if device_id and row["device_id"] != device_id:
                    other = conn.execute(
                        "SELECT id FROM users WHERE device_id = ? AND id != ?",
                        (device_id, user_id),
                    ).fetchone()
                    if other:
                        # 合并：other → user_id
                        conn.execute(
                            "UPDATE messages SET user_id = ? WHERE user_id = ?",
                            (user_id, other["id"]),
                        )
                        conn.execute(
                            "DELETE FROM users WHERE id = ?", (other["id"],),
                        )
                    conn.execute(
                        "UPDATE users SET device_id = ? WHERE id = ?",
                        (device_id, user_id),
                    )
                _touch(user_id, conn)
                conn.commit()
                return user_id

        # Step 2: 找 device match
        if device_id is not None:
            row = conn.execute(
                "SELECT id FROM users WHERE device_id = ?", (device_id,),
            ).fetchone()
            if row:
                user_id = row["id"]
                if telegram_id is not None:
                    conn.execute(
                        "UPDATE users SET telegram_id = ? WHERE id = ?",
                        (telegram_id, user_id),
                    )
                _touch(user_id, conn)
                conn.commit()
                return user_id

        # Step 3: 都不存在 → 新建
        cur = conn.execute(
            "INSERT INTO users (telegram_id, device_id) VALUES (?, ?)",
            (telegram_id, device_id),
        )
        user_id = cur.lastrowid
        conn.commit()
        return user_id


def _touch(user_id: int, conn: sqlite3.Connection) -> None:
    """更新 last_seen_at。"""
    conn.execute(
        "UPDATE users SET last_seen_at = strftime('%s','now') WHERE id = ?",
        (user_id,),
    )


# ---------- 消息 ----------
def append_message(
    user_id: int,
    role: str,
    content: str,
    channel: str,
) -> int:
    """插入一条消息，返回 message id。"""
    if role not in ("system", "user", "assistant"):
        raise ValueError(f"role 必须是 system/user/assistant，得到 {role!r}")
    if channel not in ("telegram", "xiaozhi"):
        raise ValueError(f"channel 必须是 telegram/xiaozhi，得到 {channel!r}")
    with _lock:
        conn = get_conn()
        cur = conn.execute(
            "INSERT INTO messages (user_id, role, content, channel) VALUES (?, ?, ?, ?)",
            (user_id, role, content, channel),
        )
        _touch(user_id, conn)
        conn.commit()
        return cur.lastrowid


def get_history(user_id: int, limit: int = 30) -> List[dict]:
    """拿最近 limit 条消息（按时间正序）。"""
    with _lock:
        conn = get_conn()
        rows = conn.execute(
            "SELECT role, content, channel, ts FROM messages WHERE user_id = ? ORDER BY ts DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    # 反转成正序（最早的在前）
    rows = list(reversed(rows))
    return [
        {"role": r["role"], "content": r["content"], "channel": r["channel"], "ts": r["ts"]}
        for r in rows
    ]


def get_history_formatted(user_id: int, limit: int = 30) -> str:
    """拿历史 + 渲染成文本（用于插到 LLM system prompt 里让『她』记得对方）。"""
    rows = get_history(user_id, limit=limit)
    if not rows:
        return "（这还是第一次对话，没有历史）"
    lines = []
    for r in rows:
        # 只列 user 和 assistant
        if r["role"] == "system":
            continue
        tag = "他" if r["role"] == "user" else "你"
        lines.append(f"[{r['channel']}] {tag}: {r['content']}")
    return "\n".join(lines)


def reset_history(user_id: int) -> None:
    """清空一个 user 的所有历史（/reset 命令）。"""
    with _lock:
        conn = get_conn()
        conn.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
        conn.commit()


def stats() -> dict:
    """db 健康检查（调试用）。"""
    with _lock:
        conn = get_conn()
        nu = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        nm = conn.execute("SELECT COUNT(*) AS n FROM messages").fetchone()["n"]
        # 最近用户活跃排行
        rec = conn.execute(
            "SELECT id, telegram_id, device_id, last_seen_at FROM users ORDER BY last_seen_at DESC LIMIT 5"
        ).fetchall()
    return {
        "users": nu,
        "messages": nm,
        "recent": [dict(r) for r in rec],
    }


if __name__ == "__main__":
    init_db()
    print("DB stats:", stats())
