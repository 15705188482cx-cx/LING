# -*- coding: utf-8 -*-
"""朋友圈数据层（ling 自有，存 ling_data.db，不碰 chat_db）。

复用 idempotency.py / profile.py 的模式：同 DB 文件 + 线程锁 + 单连接 +
CREATE TABLE IF NOT EXISTS。表结构见 BACKEND_INTEGRATION_V0.2.md §6。

5 张表：
- moments          朋友圈正文（author/content/images/ts/source）
- moment_likes     点赞（moment_id+name 联合主键，幂等切换）
- moment_comments  评论（含 LLM 生成的 reply + reply_emotion）
- moment_templates 预设发圈模板库（used=0/1 标记是否用过）
- moments_config   单行配置（post_interval_sec 等）

首次建表时自动：灌 15 条模板 + 3 条种子朋友圈（带回溯时间戳），让首启 feed 不空。
"""
import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

DB_PATH = str(Path(__file__).resolve().parent / "ling_data.db")

# 预设发圈模板（她口吻的日常动态）。前 3 条用于首启种子，会被标记 used=1。
_SEED_TEMPLATES = [
    "今天台球又赢了三局 哼哼",
    "深夜放毒 烧烤真香",
    "王者荣耀连跪五把 心态崩了",
    "下班路上的晚霞好好看",
    "今天做了个新发型 你们觉得怎么样",
    "又加班 到家都十点了 累死",
    "周末一个人逛街也没意思",
    "刚看完一部电影 哭得稀里哗啦",
    "今天买了杯奶茶 全糖去冰 快乐很简单",
    "健身第三天 腿已经不是我的了",
    "你们说熬夜玩手机算不算熬夜",
    "今天被老板夸了 开心了一整天",
    "下雨天就想睡觉 谁也别叫我",
    "新买的口红颜色绝了 自拍一张",
    "减肥从明天开始 今天先吃顿好的",
]

_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        c = _conn
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS moments (
                id TEXT PRIMARY KEY,
                author TEXT NOT NULL,
                content TEXT NOT NULL,
                images TEXT,
                ts REAL NOT NULL,
                source TEXT
            )
            """
        )
        c.execute("CREATE INDEX IF NOT EXISTS idx_moments_ts ON moments(ts)")
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS moment_likes (
                moment_id TEXT NOT NULL,
                name TEXT NOT NULL,
                ts REAL NOT NULL,
                PRIMARY KEY (moment_id, name)
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS moment_comments (
                id TEXT PRIMARY KEY,
                moment_id TEXT NOT NULL,
                name TEXT NOT NULL,
                text TEXT NOT NULL,
                reply TEXT,
                reply_emotion TEXT,
                ts REAL NOT NULL
            )
            """
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_comments_moment ON moment_comments(moment_id)"
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS moment_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                images TEXT,
                category TEXT,
                used INTEGER DEFAULT 0
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS moments_config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        # ---- 首启种子 ----
        # 默认发圈间隔 5 分钟
        c.execute(
            "INSERT OR IGNORE INTO moments_config (key, value) VALUES ('post_interval_sec', '300')"
        )
        # 灌模板（仅表空时）
        cur = c.execute("SELECT COUNT(*) FROM moment_templates")
        if cur.fetchone()[0] == 0:
            for content in _SEED_TEMPLATES:
                c.execute(
                    "INSERT INTO moment_templates (content, images, category, used) VALUES (?, NULL, ?, 0)",
                    (content, "日常"),
                )
        # 种子 3 条朋友圈（仅 moments 表空时），取前 3 个模板，标记 used=1
        cur = c.execute("SELECT COUNT(*) FROM moments")
        if cur.fetchone()[0] == 0:
            cur = c.execute(
                "SELECT id, content FROM moment_templates ORDER BY id LIMIT 3"
            )
            seeds = cur.fetchall()
            now = time.time()
            for i, (tid, content) in enumerate(seeds):
                mid = "m_seed_" + uuid.uuid4().hex[:8]
                c.execute(
                    "INSERT INTO moments (id, author, content, images, ts, source) "
                    "VALUES (?, ?, ?, NULL, ?, ?)",
                    (mid, "刘嘉玲", content, now - (i + 1) * 3600, "来自朋友圈"),
                )
                c.execute("UPDATE moment_templates SET used=1 WHERE id=?", (tid,))
        c.commit()
    return _conn


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


# ---------- 查询 ----------

def list_moments(limit: int = 20, before: Optional[float] = None) -> tuple[list, bool]:
    """拉朋友圈列表（ts 降序）。返回 (items, has_more)。

    items 每条带 likes / comments（comments 按 ts 正序）。
    """
    with _lock:
        conn = _get_conn()
        if before is not None:
            cur = conn.execute(
                "SELECT id, author, content, images, ts, source FROM moments "
                "WHERE ts < ? ORDER BY ts DESC LIMIT ?",
                (before, limit + 1),
            )
        else:
            cur = conn.execute(
                "SELECT id, author, content, images, ts, source FROM moments "
                "ORDER BY ts DESC LIMIT ?",
                (limit + 1,),
            )
        rows = cur.fetchall()
    has_more = len(rows) > limit
    rows = rows[:limit]
    if not rows:
        return [], has_more

    ids = [r[0] for r in rows]
    with _lock:
        conn = _get_conn()
        # 批量取点赞
        likes_map: dict[str, list] = {}
        for mid in ids:
            cur = conn.execute(
                "SELECT name FROM moment_likes WHERE moment_id=? ORDER BY ts",
                (mid,),
            )
            likes_map[mid] = [{"name": n} for (n,) in cur.fetchall()]
        # 批量取评论
        comments_map: dict[str, list] = {}
        placeholders = ",".join("?" * len(ids))
        cur = conn.execute(
            f"SELECT id, moment_id, name, text, reply, reply_emotion, ts "
            f"FROM moment_comments WHERE moment_id IN ({placeholders}) ORDER BY ts",
            ids,
        )
        for cid, mid, name, text, reply, reply_emotion, ts in cur.fetchall():
            c = {"id": cid, "name": name, "text": text, "ts": ts}
            if reply is not None:
                c["reply"] = reply
            if reply_emotion is not None:
                c["reply_emotion"] = reply_emotion
            comments_map.setdefault(mid, []).append(c)

    items = []
    for mid, author, content, images_json, ts, source in rows:
        m = {
            "id": mid,
            "author": author,
            "content": content,
            "images": [],
            "ts": ts,
            "likes": likes_map.get(mid, []),
            "comments": comments_map.get(mid, []),
        }
        if images_json:
            try:
                m["images"] = json.loads(images_json)
            except Exception:
                m["images"] = []
        if source:
            m["source"] = source
        items.append(m)
    return items, has_more


def get_moment_content(moment_id: str) -> Optional[str]:
    """取单条朋友圈正文（评论路由用，只需 content 给 LLM 当上下文）。"""
    with _lock:
        cur = _get_conn().execute(
            "SELECT content FROM moments WHERE id=?", (moment_id,)
        )
        row = cur.fetchone()
    return row[0] if row else None


def count_new_since(since: float) -> int:
    """统计 author=刘嘉玲 且 ts > since 的动态数（红点用）。"""
    with _lock:
        cur = _get_conn().execute(
            "SELECT COUNT(*) FROM moments WHERE author=? AND ts > ?",
            ("刘嘉玲", since),
        )
        return cur.fetchone()[0]


# ---------- 写入 ----------

def add_moment(
    author: str,
    content: str,
    images: Optional[list] = None,
    source: Optional[str] = None,
    ts: Optional[float] = None,
) -> str:
    """插入一条朋友圈，返回 id。"""
    mid = _new_id("m")
    if ts is None:
        ts = time.time()
    images_json = json.dumps(images) if images else None
    with _lock:
        conn = _get_conn()
        conn.execute(
            "INSERT INTO moments (id, author, content, images, ts, source) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (mid, author, content, images_json, ts, source),
        )
        conn.commit()
    return mid


def toggle_like(moment_id: str, name: str) -> tuple[bool, int]:
    """点赞/取消点赞（幂等切换）。返回 (操作后是否已赞, 操作后点赞总数)。"""
    with _lock:
        conn = _get_conn()
        cur = conn.execute(
            "SELECT 1 FROM moment_likes WHERE moment_id=? AND name=?",
            (moment_id, name),
        )
        exists = cur.fetchone() is not None
        if exists:
            conn.execute(
                "DELETE FROM moment_likes WHERE moment_id=? AND name=?",
                (moment_id, name),
            )
            liked = False
        else:
            conn.execute(
                "INSERT INTO moment_likes (moment_id, name, ts) VALUES (?, ?, ?)",
                (moment_id, name, time.time()),
            )
            liked = True
        cur = conn.execute(
            "SELECT COUNT(*) FROM moment_likes WHERE moment_id=?",
            (moment_id,),
        )
        count = cur.fetchone()[0]
        conn.commit()
    return liked, count


def add_comment(
    moment_id: str,
    name: str,
    text: str,
    reply: Optional[str] = None,
    reply_emotion: Optional[str] = None,
) -> str:
    """插入一条评论，返回 comment_id。reply/reply_emotion 可空（非"我"评论无回复）。"""
    cid = _new_id("c")
    with _lock:
        conn = _get_conn()
        conn.execute(
            "INSERT INTO moment_comments (id, moment_id, name, text, reply, reply_emotion, ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (cid, moment_id, name, text, reply, reply_emotion, time.time()),
        )
        conn.commit()
    return cid


# ---------- 模板 ----------

def pick_template() -> Optional[tuple[str, list]]:
    """随机选一条未用过的模板，标记 used=1，返回 (content, images)。库空返回 None。"""
    with _lock:
        conn = _get_conn()
        cur = conn.execute(
            "SELECT id, content, images FROM moment_templates WHERE used=0 "
            "ORDER BY RANDOM() LIMIT 1"
        )
        row = cur.fetchone()
        if not row:
            return None
        tid, content, images_json = row
        conn.execute("UPDATE moment_templates SET used=1 WHERE id=?", (tid,))
        conn.commit()
    images = []
    if images_json:
        try:
            images = json.loads(images_json)
        except Exception:
            pass
    return content, images


def reset_templates() -> None:
    """重置所有模板 used=0，让模板循环复用（模板耗尽时调用）。"""
    with _lock:
        conn = _get_conn()
        conn.execute("UPDATE moment_templates SET used=0")
        conn.commit()


# ---------- 配置 ----------

def get_config() -> dict:
    """读取发圈配置。返回 {post_interval_sec: int}。"""
    with _lock:
        cur = _get_conn().execute(
            "SELECT value FROM moments_config WHERE key='post_interval_sec'"
        )
        row = cur.fetchone()
    try:
        val = int(row[0]) if row else 300
    except (ValueError, TypeError):
        val = 300
    return {"post_interval_sec": val}


def set_post_interval(sec: int) -> None:
    """更新发圈间隔（秒）。"""
    with _lock:
        conn = _get_conn()
        conn.execute(
            "INSERT INTO moments_config (key, value) VALUES ('post_interval_sec', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(int(sec)),),
        )
        conn.commit()
