# -*- coding: utf-8 -*-
"""idempotency 幂等去重单测——用临时 DB 文件，不污染正式 ling_data.db。"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import idempotency


def setup_module(module):
    """所有测试共用一个临时内存级隔离：重置模块级 _conn，指向临时文件。"""
    import tempfile
    tmp = Path(tempfile.gettempdir()) / "ling_idem_test.db"
    if tmp.exists():
        tmp.unlink()
    idempotency.DB_PATH = str(tmp)
    idempotency._conn = None  # 强制下次 _get_conn 重建


def teardown_module(module):
    if idempotency._conn:
        idempotency._conn.close()
        idempotency._conn = None
    tmp = Path(idempotency.DB_PATH)
    if tmp.exists():
        tmp.unlink()


class TestIdempotency:
    def test_empty_id_passthrough(self):
        assert idempotency.get("") is None
        idempotency.put("", "x", "日常")  # no-op, no crash
        assert idempotency.get("") is None

    def test_put_then_get_hit(self):
        idempotency.put("id1", "在呢", "撒娇")
        assert idempotency.get("id1") == {"reply": "在呢", "emotion": "撒娇"}

    def test_miss_returns_none(self):
        assert idempotency.get("never-exists") is None

    def test_different_ids_not_cross_contaminated(self):
        idempotency.put("a", "回复A", "日常")
        idempotency.put("b", "回复B", "冷淡")
        assert idempotency.get("a")["reply"] == "回复A"
        assert idempotency.get("b")["reply"] == "回复B"

    def test_duplicate_put_keeps_first(self):
        idempotency.put("dup", "首次", "撒娇")
        idempotency.put("dup", "覆盖", "冷淡")  # INSERT OR IGNORE 忽略
        assert idempotency.get("dup") == {"reply": "首次", "emotion": "撒娇"}

    def test_ttl_expiry_returns_none(self, monkeypatch):
        idempotency.put("ttl", "过期内容", "日常")
        # 快进到 TTL 之后
        future = time.time() + idempotency.TTL_SECONDS + 1
        monkeypatch.setattr(time, "time", lambda: future)
        assert idempotency.get("ttl") is None

    def test_clear_wipes_all(self):
        idempotency.put("c1", "x", "日常")
        idempotency.put("c2", "y", "撒娇")
        idempotency.clear()
        assert idempotency.get("c1") is None
        assert idempotency.get("c2") is None
