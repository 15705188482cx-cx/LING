# -*- coding: utf-8 -*-
"""核心编排层：LLM 调用 + emotion 解析 + TTS 代理 + 记忆/DB 封装。

LingBackend 在 api_server 启动时实例化一次：
- 加载 FAISS 记忆库（复用 MemoryRetriever）
- 初始化 SQLite 共享层（复用 chat_db）+ 建固定 web 用户
- 加载 SKILL_CORE 人格 + emotion 输出指令

不 import 老的 chatbot/bot.py（它加载即读 TELEGRAM_BOT_TOKEN 会崩 + 耦合 telegram），
其 call_llm / clean_response 逻辑在本文件重新实现。
"""
import json
import logging
import re
import time
from contextlib import nullcontext
from datetime import datetime
from typing import Optional

import httpx
from openai import OpenAI

import config
from text_utils import (
    strip_thinking,
    clean_response,
    parse_emotion_reply,
    guess_emotion,
)
from memory_retriever import MemoryRetriever
from chat_db import (
    init_db,
    get_or_create_user,
    append_message,
    get_history as db_get_history,
    reset_history as db_reset_history,
)

logger = logging.getLogger(__name__)

# trace 为 None 时的占位上下文（with 语句不计时直接执行）
_noop_ctx = nullcontext


class LingBackend:
    """刘嘉玲 web 后端核心。线程安全由 chat_db 内部 RLock 保证；
    LLM/HTTP 客户端本身线程安全。FastAPI 用线程池跑同步路由，可直接复用。
    """

    def __init__(self):
        # 1. 记忆检索（FAISS 6160 条），失败静默降级
        self.memory = MemoryRetriever(slug="lijialing")

        # 2. SQLite 共享层 + 建固定 web 用户
        init_db()
        self.user_id = get_or_create_user(device_id=config.DEVICE_ID)
        logger.info(f"web 用户 user_id={self.user_id} (device_id={config.DEVICE_ID})")

        # 3. 人格 system prompt + emotion 输出契约（分两条消息：developer 契约 + system 人格）
        # 分离的原因：全塞 system 里时 M3 的人格会压倒 JSON 格式要求，导致纯文本回退。
        # developer role 是元指令，system role 是角色设定，M3 会同时遵守两者。
        system_core = config.SKILL_CORE_PATH.read_text(encoding="utf-8")
        self.developer_prompt = config.EMOTION_INSTRUCTION
        self.system_prompt = system_core

        # 4. LLM 客户端（OpenAI 兼容，MiniMax 等）
        self.llm = OpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL)

        # 5. VLM 视觉理解（复用 MiniMax 凭证，abab6.5s-chat）
        from vlm import VLM
        self.vlm = VLM()

    # ---------- 主流程 ----------

    def chat(self, text: str, trace: Optional["RequestTrace"] = None) -> tuple[str, str]:
        """文字 → (reply, emotion)。

        1. user 消息入库
        2. 读历史 + 检索记忆，拼 system prompt
        3. 调 LLM（要求输出 {emotion, reply} JSON），30s 超时 + 重试 1 次
        4. 解析 JSON，失败回退 emotion=日常 + 清洗后的原文
        5. assistant 回复入库

        trace 非 None 时记录各阶段耗时；LLM 失败抛 ChatError。
        """
        from errors import ChatError, UPSTREAM_TIMEOUT, UPSTREAM_UNAVAILABLE, RESPONSE_INVALID

        user_id = self.user_id

        # 即便后续失败，user 消息也算"这事发生过"
        with (trace.stage("db_user") if trace else _noop_ctx()):
            append_message(user_id, "user", text, "xiaozhi")

        with (trace.stage("history") if trace else _noop_ctx()):
            history = db_get_history(user_id, limit=config.MAX_HISTORY)

        # 检索相关记忆拼进 system prompt（日期 + 人格 + 记忆）
        today = datetime.now().strftime("%Y年%m月%d日")
        system_content = f"【当前日期】{today}\n\n" + self.system_prompt
        with (trace.stage("memory") if trace else _noop_ctx()):
            retrieved = self.memory.retrieve(text, history)
        if retrieved:
            system_content += (
                "\n\n## 本次相关记忆（来自真实对话录音，按相关度排序）\n"
                + retrieved
            )

        # history 只传 user 消息给 LLM：完整 history（含 assistant 回复）会让 M3
        # 模仿历史里的 emotion 倾向，导致 emotion 永远卡在"日常"不切换。
        user_only_history = [
            {"role": "user", "content": m["content"]}
            for m in history
            if m.get("role") == "user"
        ]

        messages = [
            {"role": "developer", "content": self.developer_prompt},
            {"role": "system", "content": system_content},
        ] + user_only_history

        # LLM 调用：30s 超时，失败重试 1 次（指数退避 1s）
        raw = self._call_llm_with_retry(messages, trace)
        if not raw:
            raise ChatError(RESPONSE_INVALID, "LLM 返回空内容", 502)

        # 剥离推理标签 + 解析 JSON
        cleaned = self._strip_thinking(raw)
        emotion, reply = self._parse_emotion_reply(cleaned)
        reply = self.clean_response(reply, max_length=200)

        if not reply:
            raise ChatError(RESPONSE_INVALID, "LLM 回复解析为空", 502)

        with (trace.stage("db_assistant") if trace else _noop_ctx()):
            append_message(user_id, "assistant", reply, "xiaozhi")
        logger.info(f"LLM 原始 {len(raw)} 字 → 清洗后 {len(reply)} 字, emotion={emotion}")
        return (reply, emotion)

    def _call_llm_with_retry(self, messages: list, trace=None) -> str:
        """调 LLM，30s 超时，失败重试 1 次。返回 content 或空串。

        仅对瞬时错误（超时/429/5xx/连接）重试；内容审核(422)与请求不合法(4xx)
        同输入必同错，立即抛出避免无意义重试循环。
        """
        from errors import ChatError, classify_llm_error, CONTENT_BLOCKED, RESPONSE_INVALID

        max_retries = 2  # 共 2 次（首调 + 1 次重试）
        last_err = None
        last_code = RESPONSE_INVALID
        for attempt in range(max_retries):
            stage_name = f"llm_attempt{attempt+1}"
            try:
                with (trace.stage(stage_name) if trace else _noop_ctx()):
                    response = self.llm.chat.completions.create(
                        model=config.LLM_MODEL,
                        max_tokens=1024,
                        messages=messages,
                        response_format={"type": "json_object"},
                        timeout=30.0,
                        # 关闭 M3 thinking：避免吐上千字推理再被 strip_thinking 丢弃，LLM 耗时从 10-16s 降到 2-4s
                        extra_body={"thinking": {"type": "disabled"}},
                    )
                    raw = response.choices[0].message.content.strip() if response.choices[0].message.content else ""
                    return raw
            except Exception as e:
                last_err = e
                err_code, should_retry = classify_llm_error(e)
                last_code = err_code
                logger.warning(f"LLM 第{attempt+1}次失败({err_code},retry={should_retry}): {type(e).__name__}: {e}")
                # 不可重试：立即结束，避免同输入反复触发同一错误
                if not should_retry:
                    break
                if attempt < max_retries - 1:
                    time.sleep(1.0 * (attempt + 1))  # 1s 退避
        # 全部重试失败 / 不可重试提前结束
        if last_code == CONTENT_BLOCKED:
            raise ChatError(CONTENT_BLOCKED, "内容被审核拦截，换个说法试试", 422)
        raise ChatError(last_code, f"LLM 调用失败: {type(last_err).__name__}", 502)
    def chat_stream(self, text: str):
        """流式对话：yield (sentence, emotion)。

        语音通话专用。不用 JSON 格式（流式无法先拿 emotion），改纯文本流式输出，
        按标点切句，每句 yield 一次（前端立即送 TTS 合成播放）。
        emotion 在首句前先给一个初始值（日常），流式结束后用全文重新判断补正。

        V0.3 优化：通话模式精简 prompt（history 只取近 3 轮、记忆只取 top1），
        压首 token 延迟。通话是即时的，不需要太多上下文。

        yield 顺序：
          ("", "日常")          ← 初始 emotion（前端先切头像）
          ("第一句", None)      ← 逐句文本（前端送 TTS）
          ("第二句", None)
          ...
          (None, "撒娇")        ← 最终 emotion（前端补正头像）
        """
        user_id = self.user_id
        append_message(user_id, "user", text, "xiaozhi")

        # V0.3：通话模式只取最近 3 轮历史（非 MAX_HISTORY=30），省 input token
        history = db_get_history(user_id, limit=6)
        today = datetime.now().strftime("%Y年%m月%d日")
        system_content = f"【当前日期】{today}\n\n" + self.system_prompt
        # V0.3：记忆只取 top1（通话场景即时性强，不需要大量记忆素材）
        retrieved = self.memory.retrieve(text, history, top_k=1)
        if retrieved:
            # 只取第一条记忆（retrieve 返回多段拼接，取第一段）
            first_memory = retrieved.split("\n\n")[0] if "\n\n" in retrieved else retrieved
            system_content += "\n\n## 相关记忆\n" + first_memory
        # V0.3：只传最近 3 条 user 消息（非全部）
        user_only_history = [
            {"role": "user", "content": m["content"]}
            for m in history if m.get("role") == "user"
        ][-3:]

        # 流式不用 JSON 格式（避免 emotion 等待），用普通 system prompt + 人格
        # 临时拼一个不含 JSON 契约的 developer 指令
        stream_developer = (
            "用刘嘉玲的人格回复。分2-3段短句，每段一行。不要思考过程，直接回复。"
        )
        messages = [
            {"role": "developer", "content": stream_developer},
            {"role": "system", "content": system_content},
        ] + user_only_history

        # 先 yield 初始 emotion
        yield ("", "日常")

        full_reply = []
        try:
            stream = self.llm.chat.completions.create(
                model=config.LLM_MODEL,
                max_tokens=512,
                messages=messages,
                stream=True,
                # 关闭 M3 thinking：流式下也省去等 </think> 闭合的时间，首字延迟大幅下降
                extra_body={"thinking": {"type": "disabled"}},
            )
            buf = ""
            is_first_segment = True  # 首句激进切分：遇逗号即切，压首字延迟
            # 首句无标点时的兜底最大字数：超此强制切，避免 LLM 输出无标点长句撑高首字延迟
            FIRST_SEGMENT_MAX_CHARS = 10
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                token = delta.content if delta.content else ""
                if not token:
                    continue
                # 剥离 thinking 标签内的内容（M3 流式也会带推理）
                buf += token
                # 检查是否在 thinking 标签内
                if "<think" in buf.lower() and "</think" not in buf.lower():
                    continue  # 还在推理里，攒着不输出
                # 出了 thinking 标签，清理残留
                cleaned = re.sub(r"<([a-zA-Z]+)>.*?</\1>", "", buf, flags=re.DOTALL | re.IGNORECASE)
                # 按标点切句。首句用激进标点集（逗号也切），尽快出第一个意群送 TTS；
                # 切过一次后切回句末标点（。？！；\n），避免后续被逗号切得太碎。
                # 首句无标点但超 FIRST_SEGMENT_MAX_CHARS 时强制切（兜底无标点长句）。
                while True:
                    puncts = r"[，,~、。！？；\n]" if is_first_segment else r"[。！？；\n]"
                    m = re.search(puncts, cleaned)
                    if m:
                        sentence = cleaned[:m.end()].strip()
                        cleaned = cleaned[m.end():]
                    elif is_first_segment and len(cleaned) >= FIRST_SEGMENT_MAX_CHARS:
                        # 首句无标点但已超长：在第 N 字强制切，压首字延迟
                        sentence = cleaned[:FIRST_SEGMENT_MAX_CHARS].strip()
                        cleaned = cleaned[FIRST_SEGMENT_MAX_CHARS:]
                    else:
                        break
                    buf = cleaned
                    if sentence:
                        is_first_segment = False
                        full_reply.append(sentence)
                        yield (sentence, None)
            # 收尾：剩余的也输出
            cleaned = re.sub(r"<([a-zA-Z]+)>.*?</\1>", "", buf, flags=re.DOTALL | re.IGNORECASE).strip()
            if cleaned:
                full_reply.append(cleaned)
                yield (cleaned, None)
        except Exception as e:
            logger.error(f"流式 LLM 失败: {e}")
            if not full_reply:
                yield ("网不好\n等下再发", None)

        # 全文入库 + 事后判断 emotion
        reply_text = "".join(full_reply)
        reply_text = self.clean_response(reply_text, max_length=200)
        if reply_text:
            append_message(user_id, "assistant", reply_text, "xiaozhi")

        # 事后用全文快速判断 emotion（关键词规则，避免再调一次 LLM）
        emotion = self._guess_emotion(text, reply_text)
        yield (None, emotion)

    def describe_vision(self, frame_b64: str) -> str:
        """视频帧 → VLM 描述（供 ws_server 在调 chat_stream 前先看一眼）。

        返回简短描述如"正在微笑"。失败返回空字符串。
        """
        return self.vlm.describe(
            frame_b64, question="用一句话描述画面里的人在做什么、什么表情"
        )

    def _guess_emotion(self, user_text: str, reply_text: str) -> str:
        """从对话内容快速判断 emotion（不调 LLM，关键词规则）。

        流式场景用，准确度不如 LLM 判断，但零延迟。
        """
        combined = (user_text + " " + reply_text).lower()
        if any(k in combined for k in ["急死", "怎么不回", "人呢", "快点", "催", "赶紧"]):
            return "焦急"
        if any(k in combined for k in ["睡了", "随便", "别烦", "算了", "不理"]):
            return "冷淡"
        if any(k in combined for k in ["么么", "亲", "想你了", "爱你", "宝贝", "老婆", "老公"]):
            return "调情"
        if any(k in combined for k in ["嘛", "好不好", "别生气", "人家", "求求", "哼"]):
            return "撒娇"
        return "日常"

    def chat_with_image(self, text: str, image_b64: str) -> tuple[str, str]:
        """带图的对话：图片→VLM描述→拼进user message→走chat流程→(reply, emotion)。

        VLM 把图片转成一句话描述，拼在用户文字后面作为附图说明，
        让刘嘉玲"看懂"图片后用人格回复。VLM 失败则降级为纯文字对话。
        """
        desc = self.vlm.describe(image_b64)
        if desc:
            # 拼成"用户文字 + [附图说明]"，让 LLM 知道图里有什么
            full_text = f"{text}\n[附图：{desc}]" if text else f"[发了一张图：{desc}]"
        else:
            # VLM 失败，降级：告诉她发了图但看不清
            full_text = f"{text}\n[附图：看不太清]" if text else "[发了一张图，但看不清]"
        return self.chat(full_text)

    def chat_with_vision(self, text: str, frame_b64: str) -> tuple[str, str]:
        """视频通话时的对话：摄像头帧→VLM描述→作为背景注入→走chat→(reply, emotion)。

        和 chat_with_image 的区别：视频帧是"她看到你现在的状态"（正在笑/吃饭/开车），
        作为背景上下文注入 system prompt 而非 user message，让她自然地"看到"你。
        VLM 描述要简短（"用户正在微笑"），避免干扰主对话。
        """
        desc = self.vlm.describe(
            frame_b64,
            question="用一句话描述画面里的人在做什么、什么表情",
        )
        if desc:
            # 视频帧描述作为背景注入：拼在 user message 前面
            full_text = f"[我看到你{desc}] {text}" if text else f"[我看到你{desc}]"
        else:
            full_text = text or "嗯"
        return self.chat(full_text)

    # ---------- 朋友圈（V0.2）----------

    def reply_to_comment(self, moment_content: str, comment_text: str) -> tuple[str, str]:
        """朋友圈评论 → 她的短回复 + emotion。

        复用主对话的 developer 契约（JSON {emotion, reply}）+ system 人格，
        上下文里告诉她"这是你发的朋友圈，有人评论了"，要求 1-2 句短回复。
        不写对话历史（朋友圈评论独立于聊天，不污染 chat history）。
        """
        messages = [
            {"role": "developer", "content": self.developer_prompt},
            {
                "role": "system",
                "content": (
                    self.system_prompt
                    + "\n\n## 场景：你的朋友圈\n"
                    "这是你发的一条朋友圈动态，有人给你评论了。"
                    "用你平时的语气简短回复这条评论（1-2 句话，像朋友圈回复一样随意）。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"我发的朋友圈：「{moment_content}」\n\n"
                    f"评论：「{comment_text}」"
                ),
            },
        ]
        raw = self._call_llm_with_retry(messages, None)
        cleaned = self._strip_thinking(raw)
        emotion, reply = self._parse_emotion_reply(cleaned)
        reply = self.clean_response(reply, max_length=80)
        if not reply:
            reply = "嘿嘿"
        logger.info(f"朋友圈评论回复: {len(reply)} 字, emotion={emotion}")
        return reply, emotion

    def generate_moment(self) -> str:
        """LLM 生成一条朋友圈正文（模板库用完时的兜底）。

        用 JSON {content} 格式复用 _call_llm_with_retry 的重试逻辑，
        基于 persona 生成 1-2 句自然口语的动态。失败时调用方自行兜底。
        """
        messages = [
            {
                "role": "developer",
                "content": (
                    "用刘嘉玲的人格写一条朋友圈动态。"
                    '输出 JSON：{"content":"动态正文"}。'
                    "正文 1-2 句话，像真人发圈一样自然口语化，不要加引号，不要思考过程。"
                ),
            },
            {"role": "system", "content": self.system_prompt},
        ]
        raw = self._call_llm_with_retry(messages, None)
        cleaned = self._strip_thinking(raw)
        content = ""
        try:
            obj = json.loads(cleaned)
            content = (obj.get("content") or "").strip()
        except Exception:
            content = cleaned.strip().strip('"').strip()
        content = self.clean_response(content, max_length=100) if content else ""
        if not content:
            content = "今天又是平淡的一天"
        logger.info(f"LLM 生成朋友圈: {len(content)} 字")
        return content

    def tts(self, text: str) -> bytes:
        """文字 → wav 字节。代理 mini_tts_server :8880。

        web 端 <audio> 直接播 wav，不用转 ogg/opus（那是 Telegram 的需求）。
        失败抛异常，由路由层转 502。
        """
        if not text or not text.strip():
            raise ValueError("empty text")
        resp = httpx.post(
            config.LIUJIALING_URL,
            json={"text": text.strip()},
            timeout=60.0,
        )
        resp.raise_for_status()
        return resp.content

    def history(self, limit: int = config.MAX_HISTORY) -> list[dict]:
        rows = db_get_history(self.user_id, limit=limit)
        return [{"role": r["role"], "content": r["content"], "ts": r["ts"]} for r in rows]

    def reset(self) -> None:
        db_reset_history(self.user_id)

    # ---------- 内部工具（纯逻辑委托 text_utils，保留 wrapper 便于 self 调用） ----------

    def _strip_thinking(self, raw: str) -> str:
        return strip_thinking(raw)

    def _parse_emotion_reply(self, raw: str) -> tuple[str, str]:
        return parse_emotion_reply(raw, config.EMOTIONS)

    def clean_response(self, reply: str, max_length: int = 200) -> str:
        return clean_response(reply, max_length=max_length)

    def _guess_emotion(self, user_text: str, reply_text: str) -> str:
        return guess_emotion(user_text, reply_text)
