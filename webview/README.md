# 刘嘉玲 · 微信调试客户端

微信式 Web 调试客户端，对接 `ling/backend`（FastAPI :8765），跑通
「文字 → LLM → emotion + TTS → 头像切换 + 语音播放」闭环。

视觉 1:1 还原微信移动端：微信绿 `#07C160`、气泡、底部 Tab、手机外框。

## 技术栈

Vue 3.5 + Vite 8 + TypeScript + Pinia + Vue Router (hash) + SCSS。

## 4 个 Tab

| Tab | 说明 |
|---|---|
| 消息 | 会话列表（单条=刘嘉玲）→ 聊天窗口：发文本、收回复、切情绪头像、自动播 TTS、历史恢复 |
| 通讯录 | 微信通讯录视觉壳，单联系人"刘嘉玲" → 聊天窗口 |
| 视频通话 | 本地摄像头预览 + 右上小窗 + 控制条（静音/摄像头/翻转/挂断）。阶段1不上行 |
| 设置 | 后端 health 状态、TTS/情绪标签开关、清空对话、引擎只读说明 |

## 后端契约

对接 `ling/backend`（`backend/api_server.py`）：

| 方法 | 路径 | 入参 | 出参 |
|---|---|---|---|
| POST | `/chat` | `{"text":"想你了"}` | `{"reply":"哟\n怎么想起我了","emotion":"撒娇"}` |
| GET | `/tts` | `?text=哟` | `audio/wav` |
| GET | `/health` | — | `{status,memory,db,user_id}` |
| GET | `/history` | `?limit=30` | `[{role,content,ts}]` |
| POST | `/reset` | — | `{ok:true}` |

emotion ∈ `日常/调情/撒娇/焦急/冷淡` → 切 5 种头像。

## 运行

### 1. 前提：后端 + TTS 服务已起

```bash
# 在 G:/personal project/Create-Ex 跑 control.bat 起 mini_tts_server :8880
# 再起 ling 后端
"G:/personal project/Create-Ex/voice-env/Scripts/python.exe" "G:/personal project/ling/backend/api_server.py"
# 验证
curl http://127.0.0.1:8765/health
```

### 2. 前端

```bash
cd webview
pnpm install      # 首次
pnpm dev          # 开发 → http://localhost:5173（proxy 转发到 :8765）
pnpm build        # 产出 dist/，可用 serve -s dist 静态部署
```

## 融合素材来源

| 素材 | 来源 | 协议 |
|---|---|---|
| Tab 图标 消息(n0)/通讯录(n01) 各含按下态 | `gitee.com/lakaola/chat-uniapp` | MPL-2.0 |
| 导航/工具栏 iconfont 字体 | 同上 | MPL-2.0 |
| 微信色板 | `github.com/Tencent/weui` | MIT |
| 视频通话/设置 tab 图标 | 自绘 SVG（填充剪影，匹配 n0/n01 风格） | — |
| 5 情绪占位头像 | 自绘 SVG（丢同名 png 即替换） | — |

## 情绪头像替换

`src/assets/avatars/` 下 5 个占位 SVG：`daily/flirt/coax/anxious/cold.svg`。
把真人头像以 `daily.png` `flirt.png` `coax.png` `anxious.png` `cold.png` 丢进同目录，
改 `src/components/EmotionAvatar.vue` 的 import 指向 `.png` 即替换。

## 阶段1 不做

- 不收图片/camera base64（视频通话仅本地预览）
- TTS 不分情绪切 ref（后端 mini_tts_server 写死单一 ref）
- 不做 SSE 流式
