# 刘嘉玲 · 微信调试客户端 — 功能清单与接口文档

> 微信式 Web 调试客户端，对接 `ling/backend`（FastAPI :8765），
> 跑通「文字 → LLM → emotion + TTS → 头像切换 + 语音播放」闭环。
> 视觉 1:1 还原微信移动端，4 tab 全交互。

## 目录
1. [技术栈与运行](#1-技术栈与运行)
2. [后端接口契约](#2-后端接口契约)
3. [功能清单（按 tab）](#3-功能清单按-tab)
4. [前端 store / 组件结构](#4-前端-store--组件结构)
5. [已接通的后端功能](#5-已接通的后端功能全部完成)
6. [自测结果](#6-自测结果)

---

## 1. 技术栈与运行

**栈**：Vue 3.5 + Vite 8 + TypeScript + Pinia 3 + Vue Router 4 (hash) + SCSS

**位置**：`G:/personal project/ling/webview/`（与 `backend/` 同级）

**运行**：
```bash
# 1. 起后端（+ TTS 服务 :8880）
"G:/personal project/Create-Ex/voice-env/Scripts/python.exe" "G:/personal project/ling/backend/api_server.py"

# 2. 起前端
cd webview
pnpm install      # 首次
pnpm dev          # → http://localhost:5173（proxy 转发到 :8765）
pnpm build        # 产出 dist/，serve -s dist 静态部署
```

**proxy 配置**（`vite.config.ts`）：dev 模式下 `/chat` `/chat/image` `/video/frame` `/asr` `/tts` `/stickers` `/health` `/history` `/reset` 自动转发到 `http://127.0.0.1:8765`，绕开 CORS。WS 通话直连 `ws://127.0.0.1:8766/ws/voice`（不经 proxy）。

---

## 2. 后端接口契约

三服务分工：
- `api_server.py` :8765 — HTTP API（文字/图片/TTS/ASR代理/表情包）
- `ws_server.py` :8766 — WebSocket 语音/视频通话 + HTTP `/asr`（按住说话）
- `tts_server.py` :8880 — GPT-SoVITS 独立 TTS 服务

| 方法 | 路径 | 入参 | 出参 | 说明 |
|---|---|---|---|---|
| POST | `/chat` | `{"text":"想你了"}` | `{"reply":"哟\n怎么想起我了","emotion":"撒娇"}` | 文字 → LLM → 回复+情绪 |
| POST | `/chat/image` | `{"text":"你看这个","image":"<base64>"}` | `{"reply":"...","emotion":"调情","sticker":"/stickers/调情/调情.png"}` | 图片+文字 → VLM 理解 → 回复+情绪+表情包 |
| POST | `/video/frame` | `{"text":"...","image":"<base64>"}` | `{"reply":"...","emotion":"..."}` | 视频帧+文字 → VLM 看一眼 → 回复+情绪 |
| POST | `/asr` | `{"audio":"<base64 wav>","sample_rate":16000}` | `{"text":"识别文字"}` | 按住说话：WAV→FunASR→文字 |
| GET | `/tts` | `?text=哟` | `audio/wav`（字节流） | 文字 → GPT-SoVITS → wav |
| GET | `/stickers/{emotion}/{file}` | — | `image/png` | 表情包静态资源 |
| GET | `/health` | — | `{"status":"ok","memory":true,"db":true,"user_id":16}` | 健康检查 |
| GET | `/history` | `?limit=30` | `[{"role","content","ts"},...]` | 最近对话（正序） |
| POST | `/reset` | — | `{"ok":true}` | 清空对话历史 |

### WebSocket 通话协议（:8766 `/ws/voice`）

全双工流式：音频→ASR→LLM流式分句→逐句TTS→音频回传。

**上行**（前端 → 后端）：
| 帧 | 格式 | 说明 |
|---|---|---|
| 开始一轮 | JSON `{"type":"start","sample_rate":16000}` | 后端回 `{"type":"ready"}` |
| 音频数据 | 二进制 WAV/PCM | 可分块多次发 |
| 说完一句 | JSON `{"type":"stop","sample_rate":16000}` | 触发 ASR→LLM→TTS |
| 打断 | JSON `{"type":"abort"}` | 停止当前 TTS |
| 视频帧 | JSON `{"type":"video_frame","image":"<base64>"}` | 视频模式推摄像头帧 |

**下行**（后端 → 前端）：
| 帧 | 格式 | 说明 |
|---|---|---|
| 就绪 | JSON `{"type":"ready"}` | 可开始发音频 |
| ASR 结果 | JSON `{"type":"asr_text","text":"..."}` | 识别结果（前端字幕回显） |
| LLM 分句 | JSON `{"type":"llm_chunk","text":"..."}` | 她的回复逐句 |
| 情绪 | JSON `{"type":"emotion","emotion":"撒娇"}` | 切头像 |
| TTS 开始 | JSON `{"type":"tts_start"}` | 一句 TTS 开始 |
| TTS 音频 | 二进制 WAV | 该句的语音 |
| TTS 结束 | JSON `{"type":"tts_end"}` | 一句 TTS 结束 |
| 本轮结束 | JSON `{"type":"done","reason":"..."}` | 本轮全部完成 |

**emotion 枚举**（5 种 → 切头像）：`日常` / `调情` / `撒娇` / `焦急` / `冷淡`

**闭环流程**：
```
文字对话：发文本 → POST /chat → {reply, emotion} → 切头像 → GET /tts → 播放
图片对话：选图+文字 → POST /chat/image → {reply, emotion, sticker} → 气泡显示表情包
按住说话：录音 → webm→WAV → POST /asr → 文字填输入框 → 用户编辑后发送
语音通话：WS 连接 → start → 发音频 → stop → ASR→LLM流式→TTS逐句播放
视频通话：语音通话 + 每3秒抓摄像头帧 → video_frame → VLM 看一眼注入对话
```

**固定项**：
- 后端 `DEVICE_ID="ling-web"`，独立 user（不污染 Telegram 历史）
- TTS 引擎 GPT-SoVITS :8880（刘嘉玲音色，单一 ref，不分情绪）
- LLM + VLM 统一用 MiniMax-M3（自带视觉，thinking 不暴露前端）
- ASR 用本地 FunASR SenseVoiceSmall（复用小智模型，16kHz PCM）
- 按住说话走独立 HTTP `/asr`，通话走 WS :8766（两者不共享连接）

---

## 3. 功能清单（按 tab）

### 📱 消息 tab（ChatList + ChatWindow）

#### 消息列表（ChatList.vue）
| 功能 | 状态 | 说明 |
|---|---|---|
| 会话列表 | ✅ | 单会话"刘嘉玲"，显示最后一条消息预览 + 时间 |
| 搜索栏 | ✅ | 顶部搜索框（视觉还原） |
| 未读红点 | ✅ | 离开聊天时 AI 回复 → 红点数字；进聊天清零 |
| 草稿标记 | ✅ | 未发文本存 localStorage，列表预览显示橙色 `[草稿]` |
| 长按/右键会话操作 | ✅ | ActionSheet：标为已读/置顶/免打扰/删除 |
| 点击进聊天窗口 | ✅ | |

#### 聊天窗口（ChatWindow.vue）
| 功能 | 状态 | 说明 |
|---|---|---|
| 文本发送 | ✅ | 输入框 + 发送按钮（有文本才显示） |
| 回车发送 | ✅ | Enter 发送，Shift+Enter 换行 |
| AI 回复 + 情绪头像 | ✅ | 回复按 emotion 切 5 种头像 |
| TTS 语音 | ✅ | AI 回复下方语音条，点播 /tts；设置开则自动播 |
| 历史恢复 | ✅ | 进页面调 /history 恢复 30 条 |
| 时间分隔条 | ✅ | 间隔 >5min 显示时间，跨天显示日期 |
| 草稿持久化 | ✅ | localStorage，进退保留 |
| 引用回复 | ✅ | 长按→引用，输入栏上方预览条，气泡显示引用块 |
| 长按消息菜单 | ✅ | 复制/引用/撤回(自己2min内)/多选/删除 |
| 消息撤回 | ✅ | 2分钟内可撤回，系统提示 + 5分钟内"重新编辑" |
| 拍一拍 | ✅ | 双击头像 → 系统提示"你拍了拍XX" |
| 多选模式 | ✅ | 长按→多选，底部操作条（逐条转发/合并转发/收藏/删除） |
| 发送状态 | ✅ | 发送中半透明+…，失败红!标记 |
| 系统消息行 | ✅ | 撤回/拍一拍提示，居中灰字 |
| "+"功能面板 | ✅ | 8 项网格：相册/拍摄/视频通话/位置/文件/红包/语音输入/表情 |
| 图片消息 | ✅ | 相册/拍摄选图 → POST /chat/image → VLM 看图 → 回复+表情包 |
| 按住说话 | ✅ | 录音→webm→WAV→POST /asr→文字填输入框（可编辑后发送） |
| 表情面板 | ✅ | emoji 选择器，4 分类，插入光标处 |
| 视频通话入口 | ✅ | "+"面板或联系人详情页进入 |

### 👥 通讯录 tab（Contacts + ContactDetail）

| 功能 | 状态 | 说明 |
|---|---|---|
| 搜索栏 | ✅ | |
| 功能入口行 | ✅ | 新的朋友/仅聊天的朋友/标签/公众号/企业微信联系人 |
| 联系人列表 | ✅ | 刘嘉玲（A-Z 索引头） |
| 联系人详情页 | ✅ | 资料卡：头像+昵称+微信号+地区+备注+签名 |
| 详情页操作 | ✅ | 查找聊天记录/聊天背景/免打扰/置顶/清空/视频通话/发消息 |

### 📹 视频通话 tab（VideoCall）

| 功能 | 状态 | 说明 |
|---|---|---|
| 通话方式选择 | ✅ | 语音通话 / 视频通话 |
| 呼叫状态 UI | ✅ | "正在呼叫…"（3点动画），WS 连上即"接听" |
| 通话中计时 | ✅ | mm:ss 通话时长 |
| 5 圆控制按钮 | ✅ | 静音/摄像头/翻转/扬声器/挂断 |
| 按钮样式 | ✅ | 圆形，半透黑底白图标，激活白底黑图标，挂断 #fa5151 红 |
| 本地摄像头预览 | ✅ | 右上小窗（视频模式），getUserMedia |
| 实时语音对话 | ✅ | WS :8766 录音→ASR→LLM流式→TTS逐句播放 |
| 视频帧理解 | ✅ | 每3秒抓摄像头帧→video_frame→VLM 看一眼注入对话 |
| 字幕显示 | ✅ | 识别结果 + 她的回复实时字幕 |
| 情绪切换 | ✅ | emotion 信号实时切头像 |
| 打断 | ✅ | 用户说话时可发 abort 停止她的 TTS |
| 挂断返回 | ✅ | 回聊天窗口，清理 WS/录音/AudioContext |

### ⚙️ 设置 tab（Settings）

| 功能 | 状态 | 说明 |
|---|---|---|
| 账号区 | ✅ | 刘嘉玲头像+昵称+微信号 |
| 后端状态 | ✅ | health 显示：服务/FAISS/SQLite/user_id + 刷新 |
| 深色模式 | ✅ | 跟随系统/浅色/深色，ActionSheet 选择，立即生效 |
| 字体大小 | ✅ | 小/标准/大/超大 4 档，改 html 根字号 |
| TTS 自动播放开关 | ✅ | 微信风格开关 |
| 情绪标签开关 | ✅ | 是否显示 emotion 名 |
| 引擎信息 | ✅ | TTS/LLM/后端地址（只读） |
| 清空聊天记录 | ✅ | 确认弹窗 → 调 /reset |
| 聊天背景 | ✅ | 视觉项（默认） |
| 关于 | ✅ | 视觉项 |

---

## 4. 前端 store / 组件结构

```
webview/src/
├── api/backend.ts          # 5 接口封装：chat/tts/health/history/reset
├── stores/
│   ├── chat.ts             # 消息/发送/TTS/未读/多选/撤回/拍一拍/语音转文字
│   └── settings.ts         # autoTts/showEmotionTag/theme/fontScale（持久化）
├── components/
│   ├── MessageBubble.vue   # 气泡+长按菜单+引用+撤回+语音条+多选+拍一拍
│   ├── EmotionAvatar.vue   # 5 情绪头像切换
│   ├── TabBar.vue          # 4 tab（PNG+SVG 图标）
│   └── PhoneFrame.vue      # 手机外框（9:19.5）
├── views/
│   ├── ChatList.vue        # 消息列表
│   ├── ChatWindow.vue      # 聊天窗口（核心）
│   ├── Contacts.vue        # 通讯录
│   ├── ContactDetail.vue   # 联系人详情
│   ├── VideoCall.vue       # 视频通话
│   └── Settings.vue        # 设置
├── data/emojis.ts          # emoji 数据
└── styles/
    ├── wechat.scss         # 色板（含深色模式）+ 变量
    ├── global.scss         # 重置
    └── bubble.scss         # 气泡样式
```

### chat store 关键方法
| 方法 | 作用 |
|---|---|
| `loadHistory()` | 调 /history 恢复 30 条 |
| `send(text, quote?)` | 发文本 → /chat → push 回复 → 取 TTS |
| `sendImage(file, caption)` | 选图 → POST /chat/image → VLM 看图 → 回复+表情包 |
| `transcribeAudio(blob)` | 录音 blob → webm→WAV → POST /asr → 文字（按住说话用） |
| `playMessageAudio(msg)` | 点播 AI 语音（无则取 /tts） |
| `reset()` | 调 /reset + 清本地 |
| `removeMessage(id)` | 删除单条 |
| `recallMessage(id)` | 撤回（2min 内） |
| `pat(target)` | 拍一拍 |
| `voiceToText(msg)` | 已有语音消息转文字（预留） |
| `startSelect/toggleSelect/exitSelect/deleteSelected` | 多选 |
| `enterChat/leaveChat` | 进/离聊天（控未读） |

---

## 5. 已接通的后端功能（全部完成）

| 功能 | 前端入口 | 后端接口 |
|---|---|---|
| 文字对话 | 输入框发送 | POST /chat → {reply, emotion} |
| 图片对话 | 相册/拍摄选图 | POST /chat/image → VLM + {reply, emotion, sticker} |
| 按住说话 | 长按麦克风录音 | POST /asr → 文字填输入框 |
| TTS 语音 | AI 回复语音条 | GET /tts → audio/wav |
| 表情包 | AI 回复带 sticker | GET /stickers/{emotion}/{file} |
| 语音通话 | 视频通话页选"语音" | WS :8766 /ws/voice 全双工流式 |
| 视频通话 | 视频通话页选"视频" | WS + 每3秒 video_frame → VLM 注入 |
| 情绪头像 | 全局 | emotion 字段切 5 种头像 |

### 未做（超出范围）
| 功能 | 原因 |
|---|---|
| 来电界面（AI 主动呼叫） | 需后端推送来电事件，双方都缺推送机制 |
| 多人通话 | 超出单伴侣场景 |
| 通话录音保存 | 暂无需求 |

---

## 6. 自测结果

### 后端 HTTP 联调（dev proxy :5173 → :8765）
| 测试 | 结果 |
|---|---|
| `GET /health` | ✅ `{status:ok, memory:true, db:true, user_id:16}` |
| `POST /chat {"text":"在吗"}` | ✅ `{reply:"在呢\n咋了\n嘴甜咋了嘛😏", emotion:"日常"}` |
| `POST /chat/image {"text":"你看这个","image":...}` | ✅ VLM 识别图，`{reply, emotion:"调情", sticker:"/stickers/调情/调情.png"}` |
| `POST /asr {"audio":...,"sample_rate":32000}` | ✅ `{text:"哎，今天嘴这么甜，你说不哈哈哈。"}` |
| `GET /tts?text=你好呀` | ✅ 120KB wav（RIFF/PCM 16bit mono） |
| `GET /stickers/撒娇/撒娇.png` | ✅ 200，5053 bytes |
| `GET /history?limit=3` | ✅ 返回 3 条（含刚发） |
| `POST /reset` | ✅ `{ok:true}`，清空后 history 为空 |

### 后端 WS 语音通话联调（:8766 /ws/voice）
| 测试 | 结果 |
|---|---|
| 连接 + start | ✅ 收到 `{"type":"ready"}` |
| 发 3秒 WAV + stop | ✅ 全链路通 |
| ASR 识别 | ✅ `"哎，今天嘴这么甜，你说不哈哈哈。"` |
| LLM 流式分句 | ✅ 8 句 llm_chunk |
| 情绪信号 | ✅ 2 次 emotion（初始+最终） |
| TTS 逐句音频 | ✅ 8 句 tts，共 1.2MB wav |
| done 结束 | ✅ `{"type":"done"}` |

### 前端编译
| 测试 | 结果 |
|---|---|
| `pnpm build`（vue-tsc + vite） | ✅ 类型检查通过，95 模块，~500ms |

### 代码审查修复
| 问题 | 修复 |
|---|---|
| TTS URL 被 revoke 导致重复点播失败 | playUrl 不 revoke，保留 message.audioUrl 复用 |
| 撤回"重新编辑"永远显示 | 改为撤回后 5 分钟内显示（canReedit 计算属性） |
| 录音 recStart 用 .passive 又 preventDefault 报错 | 去掉 preventDefault |
| 录音 recMove 用 target 位置不可靠 | 改用 recStart 时记录的 clientY |
| KeepAlive 下再进聊天不清未读 | 加 onActivated → enterChat |

---

## 融合素材来源

| 素材 | 来源 | 协议 |
|---|---|---|
| Tab 图标 消息(n0)/通讯录(n01) | `gitee.com/lakaola/chat-uniapp` | MPL-2.0 |
| iconfont 字体 | 同上 | MPL-2.0 |
| 微信色板 | `github.com/Tencent/weui` | MIT |
| 视频通话/设置 tab 图标 | 自绘 SVG | — |
| 5 情绪占位头像 | 自绘 SVG（丢同名 png 即替换） | — |
| 通话控制图标 + "+"面板图标 | 自绘 SVG | — |
