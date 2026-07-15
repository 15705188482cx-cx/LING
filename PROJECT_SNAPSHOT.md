# 刘嘉玲 AI 数字人伴侣 — 项目状态快照

> 生成时间：2026-07-13
> 用途：完整记录前端界面设计、后端架构、接口契约、功能清单、测试报告、已知问题
> 供独立审查使用

---

## 目录

1. [项目总览](#1-项目总览)
2. [后端架构](#2-后端架构)
3. [后端接口契约](#3-后端接口契约)
4. [前端架构](#4-前端架构)
5. [前端界面设计](#5-前端界面设计)
6. [功能清单](#6-功能清单)
7. [测试报告](#7-测试报告)
8. [已知问题与修复记录](#8-已知问题与修复记录)
9. [待验证功能](#9-待验证功能)
10. [文件清单](#10-文件清单)

---

## 1. 项目总览

### 定位
"刘嘉玲 AI 数字人伴侣"——微信式 Web 客户端 + AI 后端，实现文字/语音/视频/图片全功能对话。

### 位置
```
G:/personal project/ling/
├── backend/          # 后端（FastAPI × 3 服务）
└── webview/          # 前端（Vue 3 + Vite）
```

### 与老项目关系
- 老项目：`G:/personal project/Create-Ex/`（只读复用，不改任何文件）
- 复用内容：FAISS 记忆库（6160条）、SQLite 对话历史、人格文件 SKILL_CORE.md、FunASR SenseVoiceSmall 模型、GPT-SoVITS 音色权重、MiniMax API 凭证
- 新项目独立：新后端进程、新前端、独立 user（device_id=ling-web, user_id=16，不污染 Telegram 历史）

### 技术选型
| 层 | 技术 | 说明 |
|---|---|---|
| LLM + VLM | MiniMax-M3 | 自带视觉，thinking 在后端剥离不暴露前端 |
| ASR | FunASR SenseVoiceSmall | 本地模型，16kHz PCM，复用小智的模型文件 |
| TTS | GPT-SoVITS | 刘嘉玲音色，独立进程 :8880 |
| 记忆 | FAISS | 6160 条向量记忆 |
| 历史 | SQLite | 对话持久化 |
| 后端 | FastAPI | 3 个独立进程 |
| 前端 | Vue 3.5 + Vite 8 + TypeScript + Pinia 3 | 微信 1:1 还原 |

---

## 2. 后端架构

### 三服务分工

```
┌─────────────────────────────────────────────────────┐
│  前端 (Vue :5173)                                    │
│  ├─ 文字/图片/TTS/ASR/表情包 → vite proxy → :8765   │
│  └─ 语音/视频通话 WS → 直连 :8766                    │
└──────────┬──────────────────────────┬───────────────┘
           │                          │
           ▼                          ▼
┌─────────────────────┐    ┌─────────────────────┐
│ api_server :8765    │    │ ws_server :8766     │
│ FastAPI HTTP API    │    │ FastAPI WS + HTTP   │
│ ├─ /chat            │    │ ├─ WS /ws/voice     │
│ ├─ /chat/image      │    │ │  (语音/视频通话)   │
│ ├─ /video/frame     │    │ └─ HTTP /asr        │
│ ├─ /tts (代理8880)  │    │   (按住说话)         │
│ ├─ /asr (代理8766)  │    │                     │
│ ├─ /stickers        │    │ 加载: LingBackend   │
│ ├─ /history         │    │       + ASR         │
│ ├─ /reset           │    │       (唯一ASR实例)  │
│ └─ /health          │    └─────────────────────┘
│                     │              │
│ 加载: LingBackend   │              │ TTS 音频
│ (FAISS+DB+LLM+VLM)  │              ▼
│ 不加载 ASR(省内存)  │    ┌─────────────────────┐
└─────────────────────┘    │ tts_server :8880    │
           │               │ GPT-SoVITS          │
           │ LLM/VLM       │ 刘嘉玲音色           │
           ▼               │ gsv-env             │
    ┌─────────────┐        └─────────────────────┘
    │ MiniMax API │
    │ api.minimaxi│
    └─────────────┘
```

### 进程与依赖

| 服务 | 文件 | 环境 | 端口 | 启动命令 |
|---|---|---|---|---|
| api_server | api_server.py | voice-env | 8765 | `voice-env/Scripts/python.exe api_server.py` |
| ws_server | ws_server.py | voice-env | 8766 | `voice-env/Scripts/python.exe ws_server.py` |
| tts_server | tts_server.py | gsv-env | 8880 | `gsv-env/Scripts/python.exe tts_server.py` |
| 前端 dev | vite | node | 5173 | `cd webview && pnpm dev` |

### 模块职责

#### config.py — 配置层
- 路径常量（CREATE_EX、BACKEND_DIR、SKILL_CORE_PATH）
- sys.path 注入（复用老模块：memory_retriever、chat_db、memory_store）
- env 加载（先 chatbot/.env 拿凭证，再本地 .env 覆盖）
- 常量：LLM_MODEL=MiniMax-M3, VLM_MODEL=MiniMax-M3, PORT=8765, WS_PORT=8766, DEVICE_ID=ling-web, MAX_HISTORY=30, EMOTIONS=[日常,调情,撒娇,焦急,冷淡], EMOTION_INSTRUCTION(输出契约+few-shot)

#### core.py — LingBackend 核心类
- `__init__`: 加载 MemoryRetriever(FAISS)、init_db、get_or_create_user(user_id=16)、system_prompt(人格)、developer_prompt(输出契约)、llm client、vlm 实例
- `chat(text)`: 非流式 → JSON {emotion, reply}。流程：append user msg → user-only history → memory retrieve → developer+system messages → response_format json_object → _strip_thinking → _parse_emotion_reply → clean_response → append assistant msg
- `chat_stream(text)`: 流式生成器 → yield (sentence, emotion)。纯文本流式（无JSON），按标点分句，_guess_emotion 关键词猜情绪
- `chat_with_image(text, image_b64)`: VLM describe → "[附图：desc]" → chat()
- `chat_with_vision(text, frame_b64)`: VLM describe → "[我看到你desc]" → chat()
- `describe_vision(frame_b64)`: 返回 VLM 描述（供 ws_server 注入）
- `_strip_thinking(raw)`: 正则 `<([a-zA-Z]+)>.*?</\1>` 剥离 thinking 标签 + markdown 代码块
- `_parse_emotion_reply(cleaned)`: JSON 提取，fallback "日常"
- `_guess_emotion(user_text, reply_text)`: 关键词规则（流式时用）
- `clean_response()`: 去除 thinking/reasoning，200 字限制

#### vlm.py — VLM 类
- 用 OpenAI client + MiniMax 凭证，model=MiniMax-M3
- `describe(image_b64, question)`: image_url data URI → 文本，strip thinking + markdown

#### asr.py — ASR 类
- 包装 funasr AutoModel + SenseVoiceSmall
- MODEL_DIR = xiaozhi 路径 `G:\personal project\Create-Ex\xiaozhi-server\main\xiaozhi-server\models\SenseVoiceSmall`
- `transcribe(pcm_bytes, sample_rate=16000)`: _resample 若非 16kHz → generate() → 过滤 `<|...|>` 标签
- `_resample()`: scipy.signal.resample_poly

#### tts_server.py — 独立 TTS 服务
- GPT-SoVITS on :8880，用 gsv-env
- torchaudio monkey-patch（soundfile + scipy 替代）
- jieba_fast→jieba monkey-patch（C++ 编译工具不可用）
- POST /v1/audio/speech {"text"} → audio/wav
- GET /health → {status, warmup_done}
- 权重：liujialing-e6.ckpt + liujialing_e12_s600.pth，ref: liu_wechat_1020_0121.wav
- **依赖修复**：peft==0.12.0、onnxruntime、opencc-python-reimplemented、wordsegment

#### stickers.py — 表情包
- `pick_sticker(emotion)`: 返回 /stickers/{emotion}/{随机文件}
- `has_stickers(emotion)`: boolean
- 5 个测试 PNG（日常/调情/撒娇/焦急/冷淡）

#### api_server.py — HTTP API (:8765)
- 加载 LingBackend（FAISS+DB+LLM+VLM），**不加载 ASR**（省内存，/asr 代理到 ws_server）
- 路由：/chat, /chat/image, /video/frame, /tts(代理8880), /asr(代理8766), /stickers(StaticFiles), /history, /reset, /health
- STICKERS_DIR 用绝对路径 `Path(__file__).resolve().parent / "stickers"`

#### ws_server.py — WS + HTTP ASR (:8766)
- 加载 LingBackend + ASR（**唯一 ASR 实例**，WS 通话 + HTTP /asr 共用）
- HTTP: POST /asr, GET /health
- WS: @app.websocket("/ws/voice") → handle_connection
- handle_connection: accept → while receive() → 二进制=音频 / JSON=控制帧(start/stop/abort/video_frame)
- process_turn: 音频→ASR→[VLM帧注入]→chat_stream→逐句TTS→send_json/send_bytes 回传
- **关键修复**：Starlette 1.3.1 的 `WebSocket.send()` 要 ASGI dict，不能用裸字符串 → 全改 `send_json()`/`send_bytes()`

---

## 3. 后端接口契约

### HTTP 接口（api_server :8765）

| 方法 | 路径 | 入参 | 出参 | 说明 |
|---|---|---|---|---|
| POST | /chat | `{"text":"想你了"}` | `{"reply":"哟\n怎么想起我了","emotion":"撒娇"}` | 文字→LLM→回复+情绪 |
| POST | /chat/image | `{"text":"你看这个","image":"<base64>"}` | `{"reply":"...","emotion":"调情","sticker":"/stickers/调情/调情.png"}` | 图片+文字→VLM→回复+情绪+表情包 |
| POST | /video/frame | `{"text":"...","image":"<base64>"}` | `{"reply":"...","emotion":"..."}` | 视频帧+文字→VLM看一眼→回复+情绪 |
| POST | /asr | `{"audio":"<base64 wav>","sample_rate":16000}` | `{"text":"识别文字"}` | 按住说话：WAV→FunASR→文字（代理到8766） |
| GET | /tts | `?text=哟` | `audio/wav` 字节流 | 文字→GPT-SoVITS→wav（代理到8880） |
| GET | /stickers/{emotion}/{file} | — | image/png | 表情包静态资源 |
| GET | /health | — | `{"status":"ok","memory":true,"db":true,"user_id":16}` | 健康检查 |
| GET | /history | `?limit=30` | `[{"role","content","ts"},...]` | 最近对话（正序） |
| POST | /reset | — | `{"ok":true}` | 清空对话历史 |

**emotion 枚举**：日常 / 调情 / 撒娇 / 焦急 / 冷淡

### WebSocket 通话协议（ws_server :8766 /ws/voice）

全双工流式：音频→ASR→LLM流式分句→逐句TTS→音频回传。

**上行**（前端→后端）：
| 帧 | 格式 | 说明 |
|---|---|---|
| 开始一轮 | JSON `{"type":"start","sample_rate":16000}` | 后端回 ready |
| 音频数据 | 二进制 WAV/PCM | 可分块多次发 |
| 说完一句 | JSON `{"type":"stop","sample_rate":16000}` | 触发 ASR→LLM→TTS |
| 打断 | JSON `{"type":"abort"}` | 停止当前 TTS |
| 视频帧 | JSON `{"type":"video_frame","image":"<base64>"}` | 视频模式推摄像头帧 |

**下行**（后端→前端）：
| 帧 | 格式 | 说明 |
|---|---|---|
| 就绪 | JSON `{"type":"ready"}` | 可开始发音频 |
| ASR结果 | JSON `{"type":"asr_text","text":"..."}` | 识别结果（字幕回显） |
| LLM分句 | JSON `{"type":"llm_chunk","text":"..."}` | 她的回复逐句 |
| 情绪 | JSON `{"type":"emotion","emotion":"撒娇"}` | 切头像 |
| TTS开始 | JSON `{"type":"tts_start"}` | 一句 TTS 开始 |
| TTS音频 | 二进制 WAV | 该句的语音 |
| TTS结束 | JSON `{"type":"tts_end"}` | 一句 TTS 结束 |
| 本轮结束 | JSON `{"type":"done","reason":"..."}` | 本轮全部完成 |

### HTTP /asr 直连（ws_server :8766）
同 api_server 的 /asr，按住说话可直连这里（不经代理）。

---

## 4. 前端架构

### 技术栈
Vue 3.5 + Vite 8 + TypeScript + Pinia 3 + Vue Router 4 (hash) + SCSS

### 目录结构
```
webview/src/
├── main.ts
├── App.vue
├── api/
│   └── backend.ts          # 后端接口封装 + VoiceCallClient WS 类
├── assets/
│   └── icons/              # SVG 图标
├── components/
│   ├── EmotionAvatar.vue   # 情绪头像（5种情绪切换）
│   ├── MessageBubble.vue   # 消息气泡（文字/图片/语音条/表情包/引用/撤回）
│   ├── PhoneFrame.vue      # 手机外壳框
│   └── TabBar.vue          # 底部 4 tab
├── data/
├── router/
│   └── index.ts            # hash 路由
├── stores/
│   ├── chat.ts             # 聊天 store（消息/发送/TTS/ASR/多选）
│   └── settings.ts         # 设置 store（深色模式/字体/TTS开关）
├── styles/
│   ├── wechat.scss         # 色板（含深色模式）+ CSS 变量
│   ├── global.scss         # 重置
│   └── bubble.scss         # 气泡样式
└── views/
    ├── ChatList.vue        # 消息列表 tab
    ├── ChatWindow.vue      # 聊天窗口（文字/图片/按住说话/表情）
    ├── Contacts.vue        # 通讯录 tab
    ├── ContactDetail.vue   # 联系人详情
    ├── VideoCall.vue       # 语音/视频通话（WS）
    └── Settings.vue        # 设置 tab
```

### 路由
| 路径 | 组件 | 说明 |
|---|---|---|
| / | ChatList | 消息列表（4 tab 之一） |
| /chat | ChatList | 同上 |
| /chat/window | ChatWindow | 聊天窗口 |
| /contacts | Contacts | 通讯录 |
| /contact/:id | ContactDetail | 联系人详情 |
| /video-call | VideoCall | 语音/视频通话 |
| /settings | Settings | 设置 |

### Vite proxy 配置
```ts
proxy: {
  '/chat': '→ :8765',
  '/tts': '→ :8765',
  '/health': '→ :8765',
  '/history': '→ :8765',
  '/reset': '→ :8765',
  '/asr': '→ :8765',
  '/video/frame': '→ :8765',
  '/stickers': '→ :8765',
}
```
WS 通话直连 `ws://127.0.0.1:8766/ws/voice`（不经 proxy）。

### API 封装（api/backend.ts）
- HTTP: `chat()`, `chatWithImage()`, `videoFrame()`, `asr()`, `tts()`, `health()`, `history()`, `reset()`, `stickerUrl()`
- WS: `VoiceCallClient` 类 — `connect()`, `start(sr)`, `sendAudio(bytes)`, `stop(sr)`, `abort()`, `sendVideoFrame(b64)`, `close()`
- 回调: `onReady/onAsrText/onLlmChunk/onEmotion/onTtsStart/onTtsAudio/onTtsEnd/onDone/onError`

### chat store 关键方法
| 方法 | 作用 |
|---|---|
| `loadHistory()` | 调 /history 恢复 30 条 |
| `send(text, quote?)` | 发文本→/chat→push回复→取TTS |
| `sendImage(file, caption)` | 选图→/chat/image→VLM看图→回复+表情包 |
| `transcribeAudio(blob)` | 录音blob→webm→WAV→/asr→文字（按住说话用） |
| `playMessageAudio(msg)` | 点播AI语音（无则取/tts） |
| `reset()` | 调/reset+清本地 |
| `removeMessage(id)` | 删除单条 |
| `recallMessage(id)` | 撤回（2min内） |
| `pat(target)` | 拍一拍 |
| `startSelect/toggleSelect/exitSelect/deleteSelected` | 多选 |
| `enterChat/leaveChat` | 进/离聊天（控未读） |

### Message interface
```ts
interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  emotion?: Emotion
  ts: number
  pending?: boolean      // 发送中占位
  failed?: boolean       // 发送失败
  image?: string         // 本地图片预览 URL
  quote?: {sender, text} // 引用回复
  audioUrl?: string      // TTS 语音 URL
  audioPlayed?: boolean
  recalled?: boolean     // 已撤回
  transcript?: string    // 语音转文字
  isSystem?: boolean     // 系统提示
  sticker?: string       // 表情包 URL
}
```

---

## 5. 前端界面设计

### 整体布局
微信移动端 1:1 还原，PhoneFrame 包裹，底部 4 tab。

### 4 个 Tab

#### 📱 消息 tab（ChatList + ChatWindow）
**消息列表（ChatList.vue）**
- 单会话"刘嘉玲"，显示最后一条消息预览+时间
- 顶部搜索栏
- 未读红点（离开聊天时 AI 回复→红点，进聊天清零）
- 草稿标记（未发文本存 localStorage，列表预览橙色 `[草稿]`）
- 长按/右键会话操作（标为已读/置顶/免打扰/删除）

**聊天窗口（ChatWindow.vue）**
- 顶部导航：返回 + "刘嘉玲" 标题
- 消息列表：时间分隔条（>5min显示时间，跨天显示日期）
- 消息气泡：
  - 用户：右绿气泡（#95ec69），带头像
  - AI：左白气泡，带头像 + 情绪标签（可选）
  - 系统消息：居中灰字
  - 图片：气泡内显示图片
  - 语音条：🔈图标 + 波形 + "播放语音"
  - 表情包：气泡下方显示 sticker 图
  - 引用回复：气泡上方引用块
  - 撤回：系统提示 + 5min内"重新编辑"
  - 发送状态：发送中半透明+…，失败红!
- 长按消息菜单：复制/引用/撤回(2min)/多选/删除
- 双击头像：拍一拍
- 多选模式：底部操作条（逐条转发/合并转发/收藏/删除）
- 底部输入栏：
  - 左：🎤/⌨️ 切换（语音/键盘模式）
  - 中：文本输入框（回车发送，Shift+回车换行）
  - 右：发送按钮（有文本才显示）/ ＋号
- 语音模式：按住说话按钮（录音态/上滑取消/松开转文字）
- ＋面板 8 项：相册/拍摄/视频通话/位置/文件/红包/语音输入/表情
- 表情面板：emoji 选择器，4 分类，插入光标处
- 录音浮层：🎤 + "上滑取消，松开发送"
- 识别中浮层："识别中…"

#### 👥 通讯录 tab（Contacts + ContactDetail）
- 头像 + 昵称 + 微信号
- 详情页操作：查找聊天记录/聊天背景/免打扰/置顶/清空/视频通话/发消息

#### 📹 视频通话 tab（VideoCall）
- 3 阶段：选择(语音/视频) → 呼叫中 → 通话中
- 选择页：刘嘉玲头像 + "语音通话"/"视频通话" 按钮
- 呼叫中："正在呼叫…" + 3点动画 + 挂断按钮（WS 连上即"接听"）
- 通话中：
  - 主画面：情绪头像 + "刘嘉玲" + 通话时长 + "正在说话…" + 字幕
  - 字幕：识别结果 + 她的回复实时显示
  - 右上小窗：本地摄像头预览（视频模式）
  - 5 圆控制按钮：静音/摄像头/翻转/扬声器/挂断
  - 挂断：回聊天窗口，清理 WS/录音/AudioContext

#### ⚙️ 设置 tab（Settings）
- 账号区：刘嘉玲头像+昵称+微信号
- 后端状态：health 显示（服务/FAISS/SQLite/user_id）+ 刷新
- 深色模式：跟随系统/浅色/深色
- 字体大小：小/标准/大/超大
- TTS 自动播放开关
- 情绪标签开关
- 引擎信息（只读）
- 清空聊天记录（确认弹窗→/reset）

### 配色（wechat.scss）
| 变量 | 浅色 | 深色 |
|---|---|---|
| --wx-bg | #ededed | #000000 |
| --wx-bubble-mine | #95ec69 | #2b5e1a |
| --wx-bubble-other | #ffffff | #3a3a3c |
| --wx-text | rgba(0,0,0,0.9) | rgba(255,255,255,0.9) |
| --wx-brand | #07c160 | #07c160 |

---

## 6. 功能清单

### 已接通后端的功能（全完成）

| 功能 | 前端入口 | 后端接口 | 状态 |
|---|---|---|---|
| 文字对话 | 输入框发送 | POST /chat → {reply, emotion} | ✅ |
| 图片对话 | 相册/拍摄选图 | POST /chat/image → VLM + {reply, emotion, sticker} | ✅ |
| 按住说话 | 长按🎤录音 | POST /asr → 文字填输入框 | ✅ |
| TTS 语音 | AI 回复语音条 | GET /tts → audio/wav | ✅ |
| 表情包 | AI 回复带 sticker | GET /stickers/{emotion}/{file} | ✅ |
| 语音通话 | 视频通话页选"语音" | WS :8766 /ws/voice 全双工流式 | ✅ |
| 视频通话 | 视频通话页选"视频" | WS + 每3秒 video_frame → VLM 注入 | ✅ |
| 情绪头像 | 全局 | emotion 字段切 5 种头像 | ✅ |
| 历史恢复 | 进聊天窗口 | GET /history | ✅ |
| 清空历史 | 设置页 | POST /reset | ✅ |

### 纯前端功能（不依赖后端）

| 功能 | 说明 |
|---|---|
| 草稿持久化 | localStorage |
| 引用回复 | 长按→引用 |
| 消息撤回 | 2min内 |
| 拍一拍 | 双击头像 |
| 多选/删除 | 底部操作条 |
| emoji 表情面板 | 4 分类 |
| 深色模式 | 跟随系统/浅色/深色 |
| 字体大小 | 4 档 |

### 未做（超出范围）

| 功能 | 原因 |
|---|---|
| 来电界面（AI 主动呼叫） | 需后端推送来电事件，双方都缺推送机制 |
| 多人通话 | 超出单伴侣场景 |
| 通话录音保存 | 暂无需求 |

---

## 7. 测试报告

### 测试计划
- 文件：`backend/TEST_PLAN.md`
- 脚本：`backend/run_all_tests.py`
- 覆盖：6 节 30 用例（A 环境冒烟 / B HTTP接口 / C WS通话 / D 端到端闭环 / E 异常边界 / F 前端契约）

### 后端测试结果（30/30 通过）

| 节 | 主题 | 结果 | 亮点 |
|---|---|---|---|
| A | 环境冒烟 | 3/3 ✅ | 三服务 health 全 ok，ASR 代理识别正确，TTS 合成 94KB wav |
| B | HTTP 接口 | 9/9 ✅ | 文字/图片/视频帧/TTS/ASR/表情包/历史/reset 全通 |
| C | WS 通话 | 5/5 ✅ | 全链路 ASR→3句LLM→3段TTS(481KB)→done，打断/视频帧注入都通 |
| D | 端到端闭环 | 5/5 ✅ | 按住说话、多轮通话、图片闭环全通，5/5 情绪全覆盖 |
| E | 异常边界 | 6/6 ✅ | 空音频/静音/空文本/无效图片/空WS/断连 都不崩 |
| F | 前端契约 | 2/2 ✅ | pnpm build 560ms，7 项字段契约全匹配 |

### 关键验证点
- **D5 情绪覆盖 5/5**：撒娇/日常/焦急/冷淡/调情 全部出现
- **D2 按住说话闭环**：录音→ASR识别→LLM回复→TTS 284KB音频
- **D3 语音通话多轮**：同一WS连接跑2轮，各自ASR+done正常
- **C2 WS全链路**：音频→ASR→3句LLM流式→3段TTS(481KB)→done

### 性能
- /chat 响应：~4秒（LLM）
- /tts 合成：~1.3秒
- WS 全链路一轮：~10-15秒（ASR+LLM流式+逐句TTS）

---

## 8. 已知问题与修复记录

### 已修复

| # | 问题 | 根因 | 修复 | 影响 |
|---|---|---|---|---|
| 1 | MiniMax-M3 thinking 暴露 | M3 把 `<thinking>` 放在 content 字段 | _strip_thinking() 正则剥离 | thinking 不进前端 |
| 2 | 人格压倒 JSON 格式 | SKILL_CORE 太长，M3 拒绝 JSON | developer role(契约) + system role(人格) 分离 | JSON 稳定输出 |
| 3 | emotion 卡在"日常" | 历史 assistant 回复污染判断 | 传 user-only history 给 LLM | 5 种情绪都能出 |
| 4 | emotion 发 3 次 | ws_server 重复逻辑 | 改为 2 次（初始+最终） | 不重复 |
| 5 | gsv-env peft ImportError | peft 0.17.1 需 HybridCache | `uv pip install peft==0.12.0` | TTS 可启动 |
| 6 | jieba_fast 缺失 | C++ 编译工具不可用 | `sys.modules["jieba_fast"]=jieba` monkey-patch | 分词可用 |
| 7 | onnxruntime 缺失 | — | `uv pip install onnxruntime` | — |
| 8 | opencc 缺失 | — | `uv pip install opencc-python-reimplemented` | — |
| 9 | ASR 采样率不匹配 | test_full.wav 32kHz，FunASR 要 16kHz | asr.py 加 _resample() | — |
| 10 | api_server OOM | 两进程都加载 ASR+FAISS+LLM | api_server 不加载 ASR，/asr 代理到 ws_server | 内存减半 |
| 11 | StaticFiles 相对路径 | `directory="stickers"` 失败 | 绝对路径 `Path(__file__).resolve().parent/"stickers"` | — |
| 12 | **WS 连接必崩** | Starlette 1.3.1 的 `WebSocket.send()` 要 ASGI dict，不是裸字符串 | 全改 `send_json()`/`send_bytes()` | WS 可用 |
| 13 | **TTS 500（带英文时）** | gsv-env 缺 `wordsegment` 模块 | `uv pip install wordsegment` + 重启 | 带英文回复能合成 |
| 14 | **文字不显示**（核心bug） | `pendingMsg` 是原始对象引用，push 后改它不触发响应式 | push 后取 `messages.value[last]` 代理引用 | 文字正常显示 |
| 15 | 深色模式文字不可见 | `.bubble` 没设 color | 加 `color: var(--wx-text)` | — |
| 16 | **表情包不显示** | store 设了 sticker 字段，MessageBubble 无渲染代码 | 加 `<img class="bubble-sticker">` + 样式 | 表情包可见 |
| 17 | VideoCall 响应式隐患 | `let isSpeaking = ref()` 用 let | 改 const | — |
| 18 | 前端 WS URL 缺路径 | 连裸 `ws://127.0.0.1:8766`，后端路由是 `/ws/voice` | 补路径拼接 | — |
| 19 | VideoCall 音频格式不匹配 | MediaRecorder 产出 webm，ASR 要 WAV | 加 webmToWav() 转换 | — |
| 20 | VideoCall 缺 stop 信号 | onstop 只发音频没发 stop | 补 `wsClient.stop(16000)` | — |

### 修复原理详解：响应式代理引用问题（#14）

**Vue 3 响应式陷阱**：
```ts
// ❌ 错误写法
const pendingMsg: Message = { content: '', pending: true }
messages.value.push(pendingMsg)       // push 后 Vue 用 Proxy 包裹
pendingMsg.content = reply             // 改的是原始对象，不是代理！UI 不更新
```

```ts
// ✅ 正确写法
const pendingMsg: Message = { content: '', pending: true }
messages.value.push(pendingMsg)
const pending = messages.value[messages.value.length - 1]  // 取代理引用
pending.content = reply               // 改代理，UI 更新
```

**影响范围**：`send()` 和 `sendImage()` 两处，均已修复。

---

## 9. 待验证功能

以下功能**写了代码但从未在真实浏览器测过**，可能有同类未发现问题：

| 功能 | 风险点 | 验证方式 |
|---|---|---|
| 文字对话 | ✅ 已修复响应式问题，待浏览器确认 | 发消息看文字是否显示 |
| 发图片 | fileToBase64 + VLM 回复 + sticker 显示 | 选图发送 |
| 按住说话 | webm→WAV 转换（AudioContext 解码） | 按住🎤说话 |
| 语音通话 | MediaRecorder + WS + TTS 播放（AudioContext） | 进通话页说话 |
| 视频通话 | 摄像头帧捕获 + WS video_frame | 进视频通话 |
| 深色模式 | 各组件颜色变量是否都有 | 切深色模式 |
| 表情包显示 | sticker URL 拼接 + 图片加载 | 发图片看回复 |

---

## 10. 文件清单

### 后端（backend/）
| 文件 | 行数 | 说明 |
|---|---|---|
| config.py | ~90 | 配置层：路径/env/常量/输出契约 |
| core.py | ~310 | LingBackend 核心类：chat/chat_stream/chat_with_image/chat_with_vision |
| vlm.py | ~60 | VLM 视觉理解（MiniMax-M3） |
| asr.py | ~80 | ASR 语音识别（FunASR SenseVoiceSmall） |
| tts_server.py | ~150 | 独立 GPT-SoVITS TTS 服务 :8880 |
| stickers.py | ~40 | 表情包选择 |
| api_server.py | ~180 | HTTP API :8765 |
| ws_server.py | ~260 | WS 通话 + HTTP /asr :8766 |
| TEST_PLAN.md | — | 测试大纲 |
| run_all_tests.py | ~350 | 全流程测试脚本（30用例） |
| stickers/ | — | 5 个情绪表情包 PNG |
| test_full.wav | — | 测试音频（32kHz 3.7s） |

### 前端（webview/src/）
| 文件 | 说明 |
|---|---|
| api/backend.ts | HTTP 接口封装 + VoiceCallClient WS 类 |
| stores/chat.ts | 聊天 store（消息/发送/TTS/ASR/多选） |
| stores/settings.ts | 设置 store |
| components/MessageBubble.vue | 消息气泡（文字/图片/语音/表情包/引用/撤回） |
| components/EmotionAvatar.vue | 情绪头像 |
| components/PhoneFrame.vue | 手机外壳 |
| components/TabBar.vue | 底部 tab |
| views/ChatList.vue | 消息列表 |
| views/ChatWindow.vue | 聊天窗口 |
| views/Contacts.vue | 通讯录 |
| views/ContactDetail.vue | 联系人详情 |
| views/VideoCall.vue | 语音/视频通话 |
| views/Settings.vue | 设置 |
| styles/wechat.scss | 色板+CSS变量 |
| styles/bubble.scss | 气泡样式 |
| vite.config.ts | proxy 配置 |

---

## 附：启动顺序

```bash
# 1. TTS 服务（gsv-env）
cd "G:/personal project/ling/backend"
"G:/personal project/Create-Ex/gsv-env/Scripts/python.exe" tts_server.py

# 2. api_server（voice-env）
"G:/personal project/Create-Ex/voice-env/Scripts/python.exe" api_server.py

# 3. ws_server（voice-env）
"G:/personal project/Create-Ex/voice-env/Scripts/python.exe" ws_server.py

# 4. 前端 dev
cd "G:/personal project/ling/webview"
pnpm dev    # → http://localhost:5173

# 5. 全流程测试（可选）
cd "G:/personal project/ling/backend"
"G:/personal project/Create-Ex/voice-env/Scripts/python.exe" run_all_tests.py
```

健康检查：
```bash
curl http://127.0.0.1:8765/health   # {status:ok, memory:true, db:true, user_id:16}
curl http://127.0.0.1:8766/health   # {status:ok, asr:true}
curl http://127.0.0.1:8880/health   # {status:ok, warmup_done:true}
```
