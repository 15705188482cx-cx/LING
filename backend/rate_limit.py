# -*- coding: utf-8 -*-
"""轻量内存速率限制器（滑动窗口）。

单用户自用场景，不需要 Redis。FastAPI 同步路由跑线程池，用 threading.Lock 保护。
进程重启即清零（可接受：限流是为防误操作狂点，不是安全防线）。
"""
import threading
import time
from collections import deque


class _Window:
    """固定时长滑动窗口计数器。"""

    def __init__(self, max_count: int, window_sec: float):
        self.max = max_count
        self.window = window_sec
        self._hits: deque = deque()
        self._lock = threading.Lock()

    def allow(self) -> bool:
        """返回 True 表示放行，False 表示超限。每次调用都记账。"""
        now = time.time()
        with self._lock:
            # 清掉窗口外的旧记录
            while self._hits and now - self._hits[0] > self.window:
                self._hits.popleft()
            if len(self._hits) >= self.max:
                return False
            self._hits.append(now)
            return True


# 全局实例：发圈 60s 内最多 5 条，评论 60s 内最多 20 条
_post_limiter = _Window(5, 60.0)
_comment_limiter = _Window(20, 60.0)


def check_post() -> bool:
    """发圈限流检查。超限返回 False。"""
    return _post_limiter.allow()


def check_comment() -> bool:
    """评论限流检查。超限返回 False。"""
    return _comment_limiter.allow()
