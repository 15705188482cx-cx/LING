# 刘嘉玲 Ling 后端

刘嘉玲 AI 数字人伴侣的 web 后端，FastAPI :8765。
为前端微信式 web UI 提供 `/chat`（文字→LLM→emotion+reply）和 `/tts`（文字→wav）接口，
跑通"文字→LLM→emotion+TTS→头像切换+语音播放"闭环。

## 设计原则

- **不动老后端**：只读复用 `G:/personal project/Create-Ex` 的底层模块，不改它任何文件。
- **新起文件夹**：所有新代码在 `backend/`。
- **不 import `chatbot/bot.py`**：它加载即读 `TELEGRAM_BOT_TOKEN` 会崩 + 耦合 telegram。
  其 `call_llm` / `clean_response` 逻辑在 `core.py` 重新实现。

## 文件结构

```
backend/
├── api_server.py   # FastAPI 入口，路由 + CORS + 启动
├── core.py         # LingBackend 类：LLM+emotion解析+TTS代理+记忆+DB
├── config.py       # 路径/sys.path/env/常量
├── .env.example    # 环境变量模板
└── README.md       # 本文件
```

## 复用关系

| 老模块 | 用途 |
|---|---|
| `chatbot/memory_retriever.py` | FAISS 6160 条记忆检索，`MemoryRetriever(slug="lijialing")` |
| `shared/chat_db.py` | SQLite 对话历史，channel 归 `xiaozhi` |
| `exes/lijialing/SKILL_CORE.md` | 人格 system prompt |
| `scripts/mini_tts_server.py` | GPT-SoVITS TTS，独立进程 :8880 |

`config.py` 顶部注入 sys.path 让这些 import 生效。

## API

| 方法 | 路径 | 入参 | 出参 |
|---|---|---|---|
| POST | `/chat` | `{"text":"想你了"}` | `{"reply":"哟\n怎么想起我了","emotion":"撒娇"}` |
| GET | `/tts` | `?text=哟，怎么想起我了` | `audio/wav` |
| GET | `/health` | — | `{"status":"ok","memory":true,"db":true,"user_id":3}` |
| GET | `/history` | `?limit=30` | `[{"role","content","ts"},...]` |
| POST | `/reset` | — | `{"ok":true}` |

emotion 五选一：`日常 / 调情 / 撒娇 / 焦急 / 冷淡` → 前端切头像。

## 启动

### 1. 前提：TTS 服务已起

在 `G:/personal project/Create-Ex` 跑 `control.bat`，选 tts 启动项，
确认 `:8880 mini_tts_server LISTENING`。

### 2. 启动本后端

```bash
"G:/personal project/Create-Ex/voice-env/Scripts/python.exe" "G:/personal project/ling/backend/api_server.py"
```

voice-env 已装全 fastapi/uvicorn/openai/dotenv/httpx/faiss，无需 pip install。
LLM 凭证从 `Create-Ex/chatbot/.env` 继承，无需重复配置。

### 3. 验证

```bash
# 健康检查
curl http://127.0.0.1:8765/health

# 对话
curl -X POST http://127.0.0.1:8765/chat -H "Content-Type: application/json" -d '{"text":"在吗"}'

# TTS
curl "http://127.0.0.1:8765/tts?text=在呢" -o test.wav

# 历史
curl http://127.0.0.1:8765/history

# 清空
curl -X POST http://127.0.0.1:8765/reset
```

## 阶段1不做

- 不收图片/camera base64（前端摄像头仅本地预览）
- TTS 不分情绪切 ref（mini_tts_server 写死单一 ref）
- 不做 SSE 流式（闭环测试非流式足够）
