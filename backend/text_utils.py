# -*- coding: utf-8 -*-
"""纯文本处理工具：LLM 输出清洗 / emotion-JSON 解析 / 情绪猜测。

从 core.py 抽出，仅依赖标准库，便于在无模型环境下单测。
LingBackend 各方法是对这里的薄 wrapper（注入 config.EMOTIONS）。
"""
import json
import re


def strip_thinking(raw: str) -> str:
    """剥离 MiniMax-M3 / 推理模型的思考过程。

    M3 把推理用 <think>...</think> 塞在 content 里（非 reasoning_content 字段），
    里面有大量花括号和分析文字，会干扰 JSON 解析。先去掉它们。
    用通用 <tag>...</tag> 模式，兼容 think/thinking/reasoning 等变体。
    """
    text = re.sub(
        r"<([a-zA-Z]+)>.*?</\1>",
        "",
        raw,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # 去 markdown 代码块标记（```json ... ``` 或 ``` ... ```）
    text = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    # 兜底：若头部仍残留分析段（无闭合标签的裸推理），砍到第一个 {
    json_idx = text.find("{")
    if json_idx > 0:
        head = text[:json_idx].lower()
        if any(k in head for k in ("the user", "i should", "i need", "let me", "用户", "分析")):
            text = text[json_idx:]
    return text.strip()


def clean_response(reply: str, max_length: int = 200) -> str:
    """清洗 LLM 回复——移除思考标签、推理痕迹、限制长度。

    照搬 chatbot/bot.py 的 clean_response：她的风格就是短句，不需要解释过程。
    """
    # 1. 移除 <think> / <thinking> / <reasoning> 等思考标签
    reply = re.sub(
        r"<(think|thinking|reasoning|thought|analysis)>.*?</\1>",
        "",
        reply,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # 2. 移除自闭合的 think 标签（少见）
    reply = re.sub(
        r"<(think|thinking|reasoning|thought|analysis)/?>",
        "",
        reply,
        flags=re.IGNORECASE,
    )

    # 3. 移除"让我想想"开头的中文推理痕迹
    reply = re.sub(
        r"^(首先[，,]?让我.+?|让我想想.+?|我需要.+?|我应该.+?|接下来我.+?)\n",
        "",
        reply,
    )

    # 4. 移除推理/解释行，保留"她"的行
    lines = reply.split("\n")
    cleaned_lines = []
    skip_keywords = [
        "让我想想", "首先", "接下来", "我应该", "我需要", "思考:", "思考：",
        "分析:", "分析：", "用户说", "用户想", "我作为", "我的回复",
    ]
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if any(kw in line for kw in skip_keywords):
            continue
        cleaned_lines.append(line)

    reply = "\n".join(cleaned_lines).strip()

    # 5. 限制总长度
    if len(reply) > max_length:
        truncated = reply[:max_length]
        last_newline = truncated.rfind("\n")
        if last_newline > max_length * 0.6:
            reply = truncated[:last_newline] + "\n..."
        else:
            reply = truncated + "..."

    return reply or "嗯\n在想"


def parse_emotion_reply(raw: str, emotions: list) -> tuple[str, str]:
    """从 LLM 输出里提取 {emotion, reply} JSON。

    LLM 偶尔不守格式（套 markdown 代码块、加前后文字），用正则容错：
    匹配含 "emotion" 的 JSON。失败回退 emotion=日常, reply=原文。
    调用前应已用 strip_thinking 剥离推理，故花括号干扰较少。
    """
    # 1. 直接试整体解析（理想情况）
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return validate(data, raw, emotions)
    except Exception:
        pass

    # 2. 正则抠含 "emotion" 的 {...}（允许字符串内含花括号，非贪婪到下一个 "reply"）
    # 取最后一个匹配——LLM 偶尔先输出试探性 JSON 再输出正式的
    matches = re.findall(r'\{[^{}]*"emotion"[^{}]*\}', raw, re.DOTALL)
    for m in reversed(matches):
        try:
            data = json.loads(m)
            if isinstance(data, dict):
                return validate(data, raw, emotions)
        except Exception:
            continue

    # 3. 回退：reply 用传入的（已去推理）文本，clean_response 会再清洗
    return ("日常", raw)


def validate(data: dict, raw: str, emotions: list) -> tuple[str, str]:
    """校验 emotion 合法性，提取 reply。"""
    emotion = data.get("emotion", "日常")
    if emotion not in emotions:
        emotion = "日常"
    reply = data.get("reply", "")
    if not reply:
        reply = raw
    return (emotion, reply)


def guess_emotion(user_text: str, reply_text: str) -> str:
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
