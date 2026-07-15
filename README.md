# Ling —— 虚拟视频通话表情系统

小智 ESP32 虚拟视频通话 + 表情系统的 Web 端实现。包含文字聊天、语音通话、
视觉情绪识别、流式 TTS、朋友圈等陪伴型对话功能。

## 项目结构

```
ling/
├── backend/                 # Python 后端（FastAPI + WebSocket）
│   ├── api_server.py        # HTTP API 服务 :8765
│   ├── ws_server.py         # WebSocket 语音通话服务 :8766
│   ├── tts_server.py        # TTS 独立服务（GPT-SoVITS，:8880/:9880）
│   ├── core.py              # 核心编排：LLM + emotion + TTS + 记忆
│   ├── config.py            # 配置层：路径常量 + env 加载
│   ├── lib/                 # 复用模块本地副本（自包含，无外部依赖）
│   │   ├── chat_db.py       # SQLite 聊天历史层
│   │   ├── memory_retriever.py  # FAISS 记忆检索
│   │   └── memory_store.py  # 向量记忆库
│   ├── assets/              # 本地资源（随仓库）
│   │   ├── SKILL_CORE.md    # 人格 prompt
│   │   ├── ref_liu.wav      # TTS 参考音频
│   │   └── knowledge/       # FAISS 索引数据
│   ├── asr.py / vad.py / vlm.py / opus_codec.py
│   ├── requirements.txt     # Python 依赖
│   └── .env.example         # 环境变量模板
├── webview/                 # Vue 3 + Vite 前端
│   └── src/                 # 源码（API / stores / views / components）
└── README.md
```

## 快速开始

### 1. 后端

```bash
cd backend

# 创建虚拟环境（Python 3.10+）
python -m venv venv
source venv/Scripts/activate    # Windows Git Bash

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env，至少填写 LLM_API_KEY

# 启动 HTTP 服务
python api_server.py            # :8765

# 启动 WebSocket 语音通话服务（另一终端）
python ws_server.py             # :8766
```

### 2. 前端

```bash
cd webview
pnpm install
pnpm dev                        # :5173
```

访问 http://localhost:5173

## 环境变量说明

见 `backend/.env.example`。关键项：

| 变量 | 必填 | 说明 |
|------|------|------|
| `LLM_API_KEY` | 是 | LLM API 密钥 |
| `LLM_BASE_URL` | 是 | LLM 服务地址 |
| `LLM_MODEL` | 是 | 模型名 |
| `ASR_MODEL_DIR` | 否 | SenseVoiceSmall 模型目录，不配则语音识别禁用 |
| `GPT_SOVITS_DIR` | 否 | GPT-SoVITS 引擎目录，tts_server 启动用 |

## 外部模型下载（不入仓库）

以下大模型需自行下载，通过环境变量指定路径：

| 模型 | 用途 | 大小 | 下载来源 | 环境变量 |
|------|------|------|----------|----------|
| SenseVoiceSmall | ASR 语音识别 | ~894MB | https://github.com/FunAudioLLM/SenseVoice | `ASR_MODEL_DIR` |
| GPT-SoVITS | TTS 语音合成 | ~26GB | https://github.com/RVC-Boss/GPT-SoVITS | `GPT_SOVITS_DIR` |
| bge-small-zh-v1.5 | 记忆 embedding | ~100MB | 首次运行自动下载（需联网） | `HF_HOME` |
| silero_vad.onnx | VAD 语音检测 | ~2.3MB | `pip install silero-vad` 自带 | `VAD_MODEL_PATH` |

> 不配置上述模型时，对应功能自动降级（文字聊天始终可用）。

## 功能模块

- **文字聊天**：SSE 流式渲染 + 逐句 TTS，支持打断
- **语音通话**：WebSocket 全双工 + SileroVAD 自动断句 + Opus 编解码
- **表情系统**：5 类情绪（日常/调情/撒娇/焦急/冷淡）驱动头像切换
- **视觉理解**：VLM 识别用户上传图片
- **记忆检索**：FAISS 向量库，对话时召回相关历史记忆
- **朋友圈**：模拟社交动态，含点赞/评论/LLM 回复

## 技术栈

- 后端：Python / FastAPI / WebSocket / OpenAI SDK / FAISS / FunASR / SileroVAD
- 前端：Vue 3 / Vite / TypeScript / Pinia / opus-recorder
- TTS：GPT-SoVITS（独立服务）
