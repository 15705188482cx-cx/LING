# 刘嘉玲 AI 数字人伴侣 — 闭环测试计划

> 覆盖后端三服务（api_server :8765 / ws_server :8766 / tts_server :8880）
> + 前端契约一致性 + 端到端场景闭环。

## 一、测试环境

| 服务 | 端口 | 职责 | 健康检查 |
|---|---|---|---|
| api_server | 8765 | HTTP API（文字/图片/TTS代理/ASR代理/表情包/历史） | `GET /health` → `{status,memory,db,user_id}` |
| ws_server | 8766 | WS 语音/视频通话 + HTTP `/asr`（按住说话） | `GET /health` → `{status,asr}` |
| tts_server | 8880 | GPT-SoVITS 刘嘉玲音色 TTS | `GET /health` → `{status,warmup_done}` |

**测试素材**：
- 音频：`test_full.wav`（32kHz mono 16bit 3.7s，含人声"哎，今天嘴这么甜…"）
- 图片：5 个情绪贴纸 PNG（冷淡/撒娇/日常/焦急/调情），可作 VLM 输入

**技术栈**：MiniMax-M3（LLM+VLM）+ FunASR SenseVoiceSmall（ASR）+ GPT-SoVITS（TTS）+ FAISS（记忆）+ SQLite（历史）

## 二、测试大纲

### A. 环境冒烟（3 项）
- A1 三服务 health 检查
- A2 api_server→ws_server /asr 代理链路
- A3 tts_server 合成可用

### B. HTTP 接口测试（api_server :8765，9 项）
- B1 `GET /health` — 健康检查 + 资源就绪
- B2 `POST /chat` — 文字对话 → reply + emotion
- B3 `POST /chat/image` — 图片对话 → VLM + reply + emotion + sticker
- B4 `POST /video/frame` — 视频帧对话 → VLM + reply + emotion
- B5 `GET /tts` — 文字 → wav
- B6 `POST /asr`（代理） — base64 wav → text
- B7 `GET /stickers/{emotion}/{file}` — 表情包静态资源
- B8 `GET /history` — 历史恢复
- B9 `POST /reset` — 清空历史

### C. WS 通话测试（ws_server :8766，5 项）
- C1 WS 连接 + start/ready 握手
- C2 语音通话全链路：音频→ASR→LLM流式→TTS逐句→done
- C3 打断 abort：TTS 播放中发 abort，应停止剩余
- C4 视频帧注入 video_frame：发帧后 ASR 结果应含 VLM 描述
- C5 HTTP /asr 直连 ws_server（不经 api_server 代理）

### D. 端到端场景闭环（5 项）
- D1 文字对话闭环：发文本→reply→emotion→TTS 播放
- D2 按住说话闭环：录音→/asr→文字→/chat→reply→TTS
- D3 语音通话多轮：WS 第一轮 done 后发第二轮 start
- D4 图片对话闭环：选图→/chat/image→VLM 识别→reply+sticker
- D5 情绪覆盖：构造不同输入，验证 5 种 emotion 都能出现

### E. 异常与边界（6 项）
- E1 空音频 → /asr 应优雅返回（空 text 或错误）
- E2 超短音频（<0.5s）→ ASR 可能空，不应崩
- E3 空文本 → /chat 应优雅处理
- E4 无效图片 base64 → /chat/image 应错误返回不崩
- E5 WS 发 stop 无音频 → 应 done(reason:empty_audio)
- E6 WS 连接后立即断开 → 服务端不应崩

### F. 前端契约一致性（2 项）
- F1 pnpm build 编译通过（vue-tsc + vite）
- F2 前端 api/backend.ts 字段契约 vs 后端实际响应核对

## 三、通过标准
- A/B/C 节全绿为**必须**
- D 节全绿为**必须**（闭环验证）
- E 节：服务不崩 + 返回明确错误 = 通过
- F 节：编译通过 + 契约一致 = 通过

## 四、测试执行
用 `G:/personal project/Create-Ex/voice-env/Scripts/python.exe` 跑 `run_all_tests.py`，
单脚本串行执行全部用例，实时打印 PASS/FAIL，末尾汇总。
