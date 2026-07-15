# -*- coding: utf-8 -*-
"""配置层：路径常量、sys.path 注入、env 加载、全局常量。

被 core.py / api_server.py 顶部 import。import 本模块即完成：
1. 把本地 lib/ 目录塞进 sys.path（复用 chat_db / memory_retriever / memory_store）
2. 加载本地 .env 拿 LLM 凭证与调参
3. 暴露所有路径/常量/env 读取值

本项目自包含，不再依赖外部 Create-Ex 目录。
"""
import os
import sys
from pathlib import Path

# ---------- 路径常量 ----------

# 新后端根目录（本文件所在目录）
BACKEND_DIR = Path(__file__).resolve().parent

# 复用模块目录（chat_db / memory_retriever / memory_store 本地副本）
LIB_DIR = BACKEND_DIR / "lib"

# 资源目录（人格文件、TTS 参考音频、FAISS 知识库索引）
ASSETS_DIR = BACKEND_DIR / "assets"

# 人格文件
SKILL_CORE_PATH = Path(os.environ.get(
    "SKILL_CORE_PATH", str(ASSETS_DIR / "SKILL_CORE.md")
))

# ---------- sys.path 注入（让 import 本地 lib 模块生效）----------
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

# ---------- env 加载 ----------
from dotenv import load_dotenv  # noqa: E402

# 仅加载本地 .env（自包含，不再继承外部 Create-Ex/chatbot/.env）
load_dotenv(BACKEND_DIR / ".env", override=True)

# ---------- env 读取 ----------

LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.minimaxi.com/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "MiniMax-M3")

# VLM 视觉模型（复用 MiniMax 凭证，用 M3 自带视觉能力，thinking 在后端剥离不暴露前端）
VLM_MODEL = os.environ.get("VLM_MODEL", "MiniMax-M3")

# GPT-SoVITS mini_tts_server 地址（独立进程，control.bat 启动 :8880）
LIUJIALING_URL = os.environ.get(
    "LIUJIALING_URL", "http://127.0.0.1:8880/v1/audio/speech"
)

# GPT-SoVITS 流式合成（api_v2.py 独立进程 :9880，streaming_mode=1 旧版分段质量最佳）
# 空字符串=禁用流式，走 LIUJIALING_URL 整句合成；非空=优先流式
TTS_STREAMING_URL = os.environ.get(
    "TTS_STREAMING_URL", "http://127.0.0.1:9880/tts"
)
# streaming_mode: 0=非流式 1=旧版分段(质量最佳,首包~1.2s) 2=真流式(质量中) 3=定长分块(质量低,首包~0.5s)
TTS_STREAMING_MODE = int(os.environ.get("TTS_STREAMING_MODE", "1"))
# 流式 TTS 参考音频（与 tts_server.py 一致，复用刘嘉玲音色）
TTS_REF_AUDIO = os.environ.get(
    "TTS_REF_AUDIO", str(ASSETS_DIR / "ref_liu.wav")
)
TTS_REF_TEXT = "她可能是想陪她对象吧"

# 本后端监听端口
PORT = int(os.environ.get("PORT", "8765"))

# WebSocket 语音通话端口
WS_PORT = int(os.environ.get("WS_PORT", "8766"))

# ---------- VAD / Opus（V0.3 语音通话）----------

# VAD 自动断句参数（SileroVAD）
VAD_THRESHOLD = float(os.environ.get("VAD_THRESHOLD", "0.5"))        # 有声确认阈值
VAD_THRESHOLD_LOW = float(os.environ.get("VAD_THRESHOLD_LOW", "0.2"))  # 无声确认阈值
VAD_SILENCE_MS = int(os.environ.get("VAD_SILENCE_MS", "600"))        # 有声→无声超此毫秒=说完

# Opus 编解码参数（与 xiaozhi/前端对齐，勿改）
OPUS_SAMPLE_RATE = 16000
OPUS_FRAME_MS = 60
OPUS_BITRATE = 24000

# ---------- 业务常量 ----------

# web 端固定用这个 device_id 建独立 user，不污染 Telegram 历史
DEVICE_ID = "ling-web"

# 每个用户保留最近多少条对话喂给 LLM
MAX_HISTORY = 30

# 5 类情绪体系 → 前端头像切换
EMOTIONS = ["日常", "调情", "撒娇", "焦急", "冷淡"]

# 输出契约（放 developer role，与 system role 的人格分离，避免人格压倒 JSON 格式）
EMOTION_INSTRUCTION = """【输出契约 - 最高优先级】
你的回复必须是合法 JSON：{"emotion":"日常|调情|撒娇|焦急|冷淡","reply":"你的回复内容"}
- 只输出 JSON 对象，不要任何其它文字、markdown、思考过程
- reply 严格分3段（每段一行短句），不要超过3段，不要长篇
- reply 可在句尾自然用 1-2 个 emoji（😊😘🥺😰😒😂等），符合语气即可，不堆砌

emotion 判断标准（严格按对方语气，积极区分，不要都给"日常"）：
- 日常：纯事务性问候/分享（在吗/吃了吗/到家了）
- 调情：对方主动说情话/亲昵（想你了/亲一个/宝贝）→ 你也回情话
- 撒娇：你向对方示弱/卖萌/求哄（别生气嘛/好不好/人家不是故意的）
- 焦急：对方催你/急了/质问（怎么不回/急死/人呢）→ 你赶紧解释安抚
- 冷淡：对方要走/说睡了/态度冷（睡了/随便/别烦）→ 你失落或赌气挽留

示例：
对方"在吗" → {"emotion":"日常","reply":"在呢\\n怎么了\\n说吧"}
对方"宝贝想你了亲一个" → {"emotion":"调情","reply":"哟\\n想我了啊\\n么么哒"}
对方"你怎么不回我消息急死了" → {"emotion":"焦急","reply":"哎呀\\n刚没看到手机\\n别急嘛宝贝"}
对方"随便你我睡了别烦我" → {"emotion":"冷淡","reply":"喂\\n怎么突然这样\\n别睡嘛"}
"""
