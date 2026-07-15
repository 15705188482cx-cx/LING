# -*- coding: utf-8 -*-
"""记忆检索封装：给 bot.py 用的薄层，启动时加载 FAISS，每条消息检索相关记忆。

用法（在 bot.py 里）：
    from memory_retriever import MemoryRetriever
    memory = MemoryRetriever(slug="lijialing")  # 启动时加载一次

    # 每条消息来时：
    retrieved = memory.retrieve(user_message)
    # retrieved 是格式化好的文本，直接拼进 system prompt
"""
import os
import sys
import time
from pathlib import Path
from typing import Optional

# 确保能 import 项目根的 memory_store
_BASE = Path(__file__).resolve().parent.parent
if str(_BASE) not in sys.path:
    sys.path.insert(0, str(_BASE))

from memory_store import MemoryStore

# 模型缓存路径
os.environ.setdefault("HF_HOME", "E:/Hermes/hf_cache")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


class MemoryRetriever:
    """启动时加载向量库，对话时检索相关记忆。

    检索失败时静默降级（返回空字符串），不影响对话。
    """

    def __init__(self, slug: str = "lijialing"):
        self.slug = slug
        self._store: Optional[MemoryStore] = None
        self._enabled = False
        self._index_mtime: float = 0.0  # 记录上次加载时的 index 文件修改时间

        try:
            self._store = MemoryStore(slug=slug)
            self._store._load()  # 加载 FAISS index + 元数据
            if self._store._index is not None:
                self._enabled = True
                self._index_mtime = self._read_mtime()
                print(f"[MemoryRetriever] ✅ 记忆库已加载: "
                      f"{self._store._index.ntotal} 条记忆", flush=True)
            else:
                print(f"[MemoryRetriever] ⚠️ 记忆库不存在，对话不带记忆检索",
                      flush=True)
        except Exception as e:
            print(f"[MemoryRetriever] ⚠️ 加载失败，降级为无记忆模式: {e}",
                  flush=True)
            self._store = None
            self._enabled = False

    def _read_mtime(self) -> float:
        """读取 FAISS index 文件的修改时间，用于热重载判断。"""
        if self._store and self._store.index_path.exists():
            return self._store.index_path.stat().st_mtime
        return 0.0

    def _maybe_reload(self):
        """检查 index 文件是否被更新过（转写脚本自动入库后会变），变了就热重载。"""
        if not self._enabled or self._store is None:
            # 库之前不存在，也可能现在有了——尝试加载
            if self._store is not None:
                cur_mtime = self._read_mtime()
                if cur_mtime > 0 and self._store._index is None:
                    try:
                        self._store._load()
                        if self._store._index is not None:
                            self._enabled = True
                            self._index_mtime = cur_mtime
                            print(f"[MemoryRetriever] 🔄 记忆库首次加载: "
                                  f"{self._store._index.ntotal} 条", flush=True)
                    except Exception as e:
                        print(f"[MemoryRetriever] 热重载失败: {e}", flush=True)
            return

        cur_mtime = self._read_mtime()
        if cur_mtime > self._index_mtime:
            try:
                self._store._load()
                self._index_mtime = cur_mtime
                if self._store._index is not None:
                    print(f"[MemoryRetriever] 🔄 记忆库已热重载: "
                          f"{self._store._index.ntotal} 条", flush=True)
                else:
                    self._enabled = False
                    print(f"[MemoryRetriever] ⚠️ 热重载后库为空", flush=True)
            except Exception as e:
                print(f"[MemoryRetriever] 热重载失败，沿用旧库: {e}",
                      flush=True)

    def retrieve(self, user_message: str,
                 history: Optional[list[dict]] = None,
                 top_k: int = 5) -> str:
        """检索相关记忆，返回格式化文本（可直接拼进 system prompt）。

        Args:
            user_message: 用户当前消息
            history: 可选，最近几条对话历史（用于增强 query）
            top_k: 返回条数

        Returns:
            格式化的记忆片段文本。检索失败返回空字符串。
        """
        if not self._enabled or self._store is None:
            # 可能库刚建好，尝试加载
            self._maybe_reload()
        if not self._enabled or self._store is None:
            return ""

        # 检查 index 是否被更新（转写脚本自动入库后会触发热重载）
        self._maybe_reload()
        if not self._enabled or self._store is None:
            return ""

        try:
            # 增强 query：如果有历史，把最近 1-2 条 user 消息拼进 query
            query = user_message
            if history:
                recent_user = [m["content"] for m in history[-4:]
                               if m.get("role") == "user"]
                if recent_user:
                    query = " ".join(recent_user[-2:]) + " " + user_message

            results = self._store.search(query, top_k=top_k)
            if not results:
                return ""

            # 格式化
            lines = []
            for r in results:
                mm = int(r["start"]) // 60
                ss = int(r["start"]) % 60
                line = (f"[录音{r['rec']} {mm:02d}:{ss:02d} | "
                        f"{r['speaker']}·{r['emotion']}] "
                        f"{r['center_text']}")
                lines.append(line)

            return "\n".join(lines)

        except Exception as e:
            print(f"[MemoryRetriever] 检索出错，降级: {e}", flush=True)
            return ""

    @property
    def enabled(self) -> bool:
        return self._enabled
