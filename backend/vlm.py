# -*- coding: utf-8 -*-
"""VLM 视觉理解封装：图片 → 文字描述。

复用 MiniMax 现有凭证（无需新 key/新厂商）。实测 MiniMax-M3 和 abab6.5s-chat
都支持 OpenAI image_url 格式。这里用 abab6.5s-chat 做描述（快、无 thinking、纯描述），
把图片转成文字后拼进主对话的 user message，让刘嘉玲用人格回复。

调用链：
  用户发图 → vlm.describe(image_b64) → "一只橘猫趴在键盘上"
  → core.chat_with_image 把描述拼进 user message → LLM 用人格回复
"""
import logging
import re

from openai import OpenAI

import config

logger = logging.getLogger(__name__)


class VLM:
    """视觉理解：图片 base64 → 简短中文描述。"""

    def __init__(self):
        # 复用 MiniMax 凭证（与主 LLM 同一个 key）
        self.client = OpenAI(
            api_key=config.LLM_API_KEY,
            base_url=config.LLM_BASE_URL,
        )
        # 用 abab6.5s-chat 做描述：快、无 thinking 推理、纯描述
        # M3 也能看图但会带 _mD 推理，描述场景不需要
        self.model = config.VLM_MODEL

    def describe(self, image_b64: str, question: str = "简短描述这张图片的内容") -> str:
        """图片 base64 → 中文描述（一句话）。

        Args:
            image_b64: 不含 data: 前缀的纯 base64 字符串
            question: 引导描述的问题，默认"简短描述这张图片的内容"

        Returns:
            图片描述文本。失败返回空字符串（降级为不理解图片）。
        """
        data_url = f"data:image/jpeg;base64,{image_b64}"
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                max_tokens=150,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": data_url}},
                            {"type": "text", "text": question + "，一句话，中文"},
                        ],
                    }
                ],
            )
            desc = resp.choices[0].message.content.strip() if resp.choices[0].message.content else ""
            # M3 会带  dismantling 推理，剥离掉（不暴露给前端）
            desc = re.sub(r"<([a-zA-Z]+)>.*?</\1>", "", desc, flags=re.DOTALL | re.IGNORECASE)
            # 去 markdown 代码块标记
            desc = re.sub(r"```(?:json)?\s*", "", desc, flags=re.IGNORECASE)
            desc = desc.replace("\n", " ").strip()
            logger.info(f"VLM 描述: {desc[:80]}")
            return desc
        except Exception as e:
            logger.error(f"VLM 调用失败: {e}")
            return ""
