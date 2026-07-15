# -*- coding: utf-8 -*-
"""text_utils 纯逻辑单测——不依赖 LLM/DB/FAISS，无模型环境下可跑。"""
import sys
from pathlib import Path

# 确保能 import backend 目录下的纯模块（不触发 config.py 的 sys.path 注入副作用，
# 因为 text_utils 顶部只 import json/re）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import text_utils as t

EMOTIONS = ["日常", "调情", "撒娇", "焦急", "冷淡"]


# ---------- strip_thinking ----------
class TestStripThinking:
    def test_clean_json_unchanged(self):
        raw = '{"emotion":"撒娇","reply":"哼"}'
        assert t.strip_thinking(raw) == raw

    def test_think_tag_removed(self):
        raw = '<think>分析用户意图</think>{"emotion":"日常","reply":"在呢"}'
        assert t.strip_thinking(raw) == '{"emotion":"日常","reply":"在呢"}'

    def test_thinking_tag_variants(self):
        for tag in ("think", "thinking", "reasoning"):
            raw = f'<{tag}>xx</{tag}>{{"emotion":"日常","reply":"嗯"}}'
            assert t.strip_thinking(raw) == '{"emotion":"日常","reply":"嗯"}'

    def test_markdown_codeblock_removed(self):
        raw = '```json\n{"emotion":"日常","reply":"在"}\n```'
        out = t.strip_thinking(raw)
        assert '{"emotion"' in out and '```' not in out

    def test_bare_reasoning_head_truncated(self):
        # 无闭合标签的裸推理头部，含触发关键词 → 砍到第一个 {
        raw = 'Let me analyze the user. {"emotion":"日常","reply":"嗯"}'
        out = t.strip_thinking(raw)
        assert out.startswith("{")

    def test_bare_reasoning_without_keyword_kept(self):
        # 头部不含触发关键词 → 保留（避免误砍正常前缀）
        raw = '你好啊 {"emotion":"日常","reply":"嗯"}'
        out = t.strip_thinking(raw)
        assert "你好啊" in out


# ---------- clean_response ----------
class TestCleanResponse:
    def test_plain_text_kept(self):
        assert t.clean_response("在呢\n怎么了\n说吧") == "在呢\n怎么了\n说吧"

    def test_think_tag_in_reply_removed(self):
        assert t.clean_response("<think>xx</think>你好") == "你好"

    def test_reasoning_lines_removed(self):
        out = t.clean_response("让我想想\n在呢\n用户说你好")
        assert "让我想想" not in out and "用户说" not in out
        assert "在呢" in out

    def test_length_truncated_with_ellipsis(self):
        long = "啊" * 300
        out = t.clean_response(long, max_length=50)
        assert len(out) <= 53 and out.endswith("...")

    def test_empty_returns_fallback(self):
        assert t.clean_response("") == "嗯\n在想"
        assert t.clean_response("   ") == "嗯\n在想"


# ---------- parse_emotion_reply ----------
class TestParseEmotionReply:
    def test_valid_json(self):
        raw = '{"emotion":"撒娇","reply":"哼嘛"}'
        assert t.parse_emotion_reply(raw, EMOTIONS) == ("撒娇", "哼嘛")

    def test_invalid_emotion_falls_back(self):
        raw = '{"emotion":"开心","reply":"哈哈"}'
        # "开心" 不在 EMOTIONS → 回退"日常"
        assert t.parse_emotion_reply(raw, EMOTIONS) == ("日常", "哈哈")

    def test_json_in_codeblock(self):
        raw = '```json\n{"emotion":"冷淡","reply":"哦"}\n```'
        # strip_thinking 先去代码块，再 parse
        assert t.parse_emotion_reply(t.strip_thinking(raw), EMOTIONS) == ("冷淡", "哦")

    def test_embedded_json_extracted(self):
        raw = '前面废话{"emotion":"焦急","reply":"急"}后面废话'
        assert t.parse_emotion_reply(raw, EMOTIONS) == ("焦急", "急")

    def test_multiple_json_takes_last(self):
        raw = '{"emotion":"日常","reply":"a"}{"emotion":"调情","reply":"b"}'
        assert t.parse_emotion_reply(raw, EMOTIONS) == ("调情", "b")

    def test_no_json_falls_back(self):
        raw = "完全不是 JSON 的纯文本"
        emotion, reply = t.parse_emotion_reply(raw, EMOTIONS)
        assert emotion == "日常"
        assert reply == raw

    def test_missing_reply_uses_raw(self):
        raw = '{"emotion":"撒娇"}'
        assert t.parse_emotion_reply(raw, EMOTIONS) == ("撒娇", raw)


# ---------- guess_emotion ----------
class TestGuessEmotion:
    def test_anxious(self):
        assert t.guess_emotion("怎么不回我啊", "") == "焦急"

    def test_cold(self):
        assert t.guess_emotion("我睡了别烦", "") == "冷淡"

    def test_flirty(self):
        assert t.guess_emotion("", "么么哒想你了") == "调情"

    def test_cute(self):
        assert t.guess_emotion("好不好嘛", "") == "撒娇"

    def test_default(self):
        assert t.guess_emotion("在吗", "在呢") == "日常"

    def test_priority_anxious_over_others(self):
        # "快点" 在焦急词表，"嘛" 在撒娇词表，焦急先判
        assert t.guess_emotion("快点回我嘛", "") == "焦急"
