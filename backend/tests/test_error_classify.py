# -*- coding: utf-8 -*-
"""errors.classify_llm_error + 错误码单测——不依赖运行时状态。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from errors import (
    classify_llm_error,
    CONTENT_BLOCKED,
    UPSTREAM_TIMEOUT,
    UPSTREAM_RATE_LIMITED,
    UPSTREAM_UNAVAILABLE,
    RETRYABLE_CODES,
    ChatError,
)


class TestClassifyLlmError:
    def test_422_sensitive_blocked(self):
        code, retry = classify_llm_error(Exception(
            "UnprocessableEntityError: Error code: 422 - input new_sensitive (1026)"
        ))
        assert code == CONTENT_BLOCKED
        assert retry is False

    def test_unprocessable_entity(self):
        code, retry = classify_llm_error(Exception("unprocessable_entity_error"))
        assert code == CONTENT_BLOCKED
        assert retry is False

    def test_timeout_retryable(self):
        code, retry = classify_llm_error(Exception("APITimeoutError: Request timed out"))
        assert code == UPSTREAM_TIMEOUT
        assert retry is True

    def test_429_rate_limited(self):
        code, retry = classify_llm_error(Exception("RateLimitError: 429 rate limit"))
        assert code == UPSTREAM_RATE_LIMITED
        assert retry is True

    def test_404_not_retryable(self):
        # 请求本身不合法（模型不存在/路径错），同输入必同错
        code, retry = classify_llm_error(Exception("NotFoundError: 404 model not found"))
        assert code == UPSTREAM_UNAVAILABLE
        assert retry is False

    def test_401_not_retryable(self):
        code, retry = classify_llm_error(Exception("AuthenticationError: 401 invalid key"))
        assert code == UPSTREAM_UNAVAILABLE
        assert retry is False

    def test_500_retryable(self):
        code, retry = classify_llm_error(Exception("InternalServerError: 500"))
        assert code == UPSTREAM_UNAVAILABLE
        assert retry is True

    def test_connection_error_retryable(self):
        code, retry = classify_llm_error(ConnectionError("Connection refused"))
        assert code == UPSTREAM_UNAVAILABLE
        assert retry is True


class TestContentBlockedNotRetryable:
    def test_not_in_retryable_set(self):
        assert CONTENT_BLOCKED not in RETRYABLE_CODES


class TestChatErrorContentBlocked:
    def test_content_blocked_not_retryable(self):
        e = ChatError(CONTENT_BLOCKED, "内容被审核拦截", 422)
        assert e.retryable is False
        assert e.status_code == 422
        assert e.to_dict()["code"] == CONTENT_BLOCKED
