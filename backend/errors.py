# -*- coding: utf-8 -*-
"""统一错误处理 + request_id + 结构化日志。

V0.1：让"偶尔没回复"可诊断。
- 每个请求生成 request_id
- /chat 各阶段记录耗时日志
- 统一错误码（前端按码显示中文提示+重试）
- LLM 超时 + 重试
"""
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("ling.request")

# ---------- 错误码 ----------
# 前端按 code 显示中文提示，retryable=true 时显示重试按钮

INVALID_INPUT = "INVALID_INPUT"                # 4xx 输入非法（空文本/超长/格式错），不重试
UPSTREAM_TIMEOUT = "UPSTREAM_TIMEOUT"          # LLM/VLM/TTS 超时，可重试
UPSTREAM_RATE_LIMITED = "UPSTREAM_RATE_LIMITED" # 429 限流，可重试
UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"  # 5xx 上游不可用，可重试
RESPONSE_INVALID = "RESPONSE_INVALID"          # LLM 返回非法 JSON/空回复，可重试
CONTENT_BLOCKED = "CONTENT_BLOCKED"            # 上游内容审核拦截（MiniMax 422 new_sensitive），不重试
INTERNAL_ERROR = "INTERNAL_ERROR"              # 后端内部异常，可重试

# 可重试的错误码集合
RETRYABLE_CODES = {
    UPSTREAM_TIMEOUT, UPSTREAM_RATE_LIMITED, UPSTREAM_UNAVAILABLE,
    RESPONSE_INVALID, INTERNAL_ERROR,
}


class ChatError(Exception):
    """带错误码的可控异常。前端按 code 展示，retryable 决定是否给重试按钮。"""

    def __init__(self, code: str, message: str, status_code: int = 500):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = code in RETRYABLE_CODES
        super().__init__(message)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }


# ---------- LLM 错误分类（纯函数，不依赖运行时状态，便于单测） ----------

def classify_llm_error(e: Exception) -> tuple[str, bool]:
    """根据 LLM 调用异常推断 (错误码, 是否值得重试)。

    重试判定原则：同输入是否会再失败。
    - 422 内容审核（new_sensitive 等）：同输入必同拦截 → 不重试
    - 其它 4xx（非 429）：请求本身不合法（同输入必同错）→ 不重试
    - 超时 / 429 限流 / 5xx / 连接错误：上游瞬时问题 → 可重试

    依据异常字符串匹配（openai 库异常类型跨版本不稳，字符串更稳）。
    """
    err_str = str(e).lower()
    # 内容审核拦截：MiniMax 422 input new_sensitive / unprocessable_entity
    if "422" in err_str or "sensitive" in err_str or "unprocessable" in err_str:
        return (CONTENT_BLOCKED, False)
    # 超时
    if "timeout" in err_str or "timed out" in err_str:
        return (UPSTREAM_TIMEOUT, True)
    # 限流
    if "429" in err_str or "rate" in err_str:
        return (UPSTREAM_RATE_LIMITED, True)
    # 其它 4xx（请求本身不合法）：同输入必同错，不重试
    # openai 异常字符串里带 "404"/"401"/"400" 等 HTTP 状态
    for code in ("404", "401", "403", "400"):
        if code in err_str:
            return (UPSTREAM_UNAVAILABLE, False)
    # 5xx 或连接错误等：上游瞬时问题，可重试
    return (UPSTREAM_UNAVAILABLE, True)


# ---------- request_id ----------

def new_request_id() -> str:
    """生成短 request_id（8 位），用于日志关联。"""
    return uuid.uuid4().hex[:8]


# ---------- 结构化阶段计时器 ----------

@dataclass
class RequestTrace:
    """一次请求的阶段耗时记录。用 with trace.stage('llm') 自动计时。"""
    request_id: str
    stages: list = field(default_factory=list)  # [(name, ms, error_or_None)]

    class _Stage:
        def __init__(self, trace, name):
            self.trace = trace
            self.name = name
            self.t0 = 0.0

        def __enter__(self):
            self.t0 = time.monotonic()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            ms = (time.monotonic() - self.t0) * 1000
            err = f"{type(exc_val).__name__}: {exc_val}" if exc_val else None
            self.trace.stages.append((self.name, round(ms), err))
            if err:
                logger.warning(
                    f"[{self.trace.request_id}] 阶段 {self.name} 失败 ({ms:.0f}ms): {err}"
                )
            return False  # 不吞异常

    def stage(self, name: str):
        return RequestTrace._Stage(self, name)

    def summary(self) -> str:
        parts = [f"{name}={ms}ms" for name, ms, _ in self.stages]
        return " ".join(parts)

    def log_summary(self, label: str = "完成"):
        total = sum(ms for _, ms, _ in self.stages)
        errors = [s for s in self.stages if s[2]]
        status = f"FAIL({errors[-1][0]})" if errors else "OK"
        logger.info(
            f"[{self.request_id}] {label} {status} 总耗时={total:.0f}ms | {self.summary()}"
        )
