# 刘嘉玲 Ling — V0.2 后端集成文档

> **给后端同学**：本文是前端 V0.2 的完整接口契约，照此实现即可接通。所有接口挂在现有 FastAPI `:8765`，前端 dev proxy 已覆盖全部根路径。
>
> 前端原则：**接口可用走真接口，失败自动降级**（朋友圈走 mock 兜底，profile 走默认值）。后端实现后前端**无需改动**即自动切换。
>
> 生成时间：2026-07-13 ｜ 前端分支：`feat/moments` ｜ `pnpm build` 通过（546ms，0 类型错误）

---

## 目录

1. [V0.2 相对 V0.1 新增了什么](#1-v02-相对-v01-新增了什么)
2. [集成前置](#2-集成前置)
3. [V0.2 新增接口契约（重点）](#3-v02-新增接口契约重点)
   - 3.1 [朋友圈 Moments（7 个接口）](#31-朋友圈-moments7-个接口)
   - 3.2 [个人资料 Profile（2 个接口）](#32-个人资料-profile2-个接口)
   - 3.3 [`/chat` 幂等增强（client_message_id）](#33-chat-幂等增强client_message_id)
   - 3.4 [新增错误码 CONTENT_BLOCKED](#34-新增错误码-content_blocked)
4. [已有接口速查（V0.1，全通，保留）](#4-已有接口速查v01全通保留)
5. [待后端实现的功能（UI 已就绪）](#5-待后端实现的功能ui-已就绪)
6. [数据库设计建议](#6-数据库设计建议)
7. [错误码与统一信封规范](#7-错误码与统一信封规范)
8. [集成验收清单](#8-集成验收清单)

---

## 1. V0.2 相对 V0.1 新增了什么

V0.1 是「单聊天窗口 + 设置页」。V0.2 把界面升级为**真微信 4 Tab 结构**，并新增**朋友圈**子系统。

### 1.1 界面结构（4 Tab）

| Tab | 文件 | 说明 |
|---|---|---|
| 消息 | `ChatList.vue` + `ChatWindow.vue` | 会话列表 + 聊天窗口（V0.1 已有，V0.2 补强交互） |
| 通讯录 | `Contacts.vue` + `ContactDetail.vue` | 联系人入口 + 资料页 |
| **发现**（新） | `Discover.vue` | 朋友圈入口 + 红点轮询（30s）；视频号/直播等 toast 占位 |
| **我**（改造） | `Me.vue` | 原 `Settings.vue` 拆成「我」页：大头像卡 + 后端状态 + 朋友圈频率 + 深色/字体 + 清空确认 |

> 视频通话保留为子页（从聊天「+」进入），不当 tab。

### 1.2 聊天窗口 V0.2 新交互（纯前端，不依赖新接口）

- 按住说话录音 UI（上滑取消）—— 走已有 `/asr`
- 表情面板（4 分类 emoji 网格）
- 多选模式（转发/收藏/删除）
- 消息撤回（2 分钟内）+ 重新编辑（5 分钟内显示）
- 拍一拍（双击头像）
- 长按消息菜单（复制/引用/撤回/多选/删除）
- 引用回复
- 草稿持久化 + 列表 `[草稿]` 标记
- 进/离聊天窗口的未读红点联动

### 1.3 需要后端的新增能力（本文重点）

| # | 能力 | 接口 | 状态 |
|---|---|---|---|
| 1 | **朋友圈**（列表/发圈/点赞/评论/红点/频率配置） | 7 个 `/moments*` | 前端 ✅，后端 ⬜ |
| 2 | **个人资料**（名字/签名/头像）持久化 | `GET/PUT /profile` | 前端 ✅，**后端已实现 ✅** |
| 3 | `/chat` 幂等去重 | `client_message_id` 字段 | 前端 ✅，**后端已实现 ✅** |
| 4 | 内容审核拦截错误码 | `CONTENT_BLOCKED` | 前端 ✅，**后端已实现 ✅** |

> 标 ⬜ 的是本文档要你实现的；标 ✅ 的后端已就绪，前端已对接，**不要改动其契约**。

---

## 2. 集成前置

### 2.1 服务与端口

| 服务 | 端口 | 现状 |
|---|---|---|
| `api_server.py`（FastAPI HTTP） | **8765** | 运行中，`/health` 返回 `{status:ok,memory:true,db:true,user_id:16}` |
| `ws_server.py`（WS 通话 + HTTP /asr） | 8766 | 按需启动（内存约束，三服务不同跑） |
| `tts_server.py`（GPT-SoVITS） | 8880 | 按需启动 |
| 前端 dev（vite） | 5173 | `cd webview && pnpm dev` |

**所有新接口都加在 `api_server.py`（:8765），不要起新端口。**

### 2.2 CORS

`api_server.py` 已 `allow_origins=["*"]`，无需额外配置。dev 下前端走 vite proxy（同源），prod/静态部署时前端 `BASE` 走 `VITE_API_BASE` 绝对地址可配。

### 2.3 前端 dev proxy（已覆盖全部根路径）

`webview/vite.config.ts` 已把以下前缀转发到 `:8765`：

```
/chat  /chat/image  /tts  /health  /history  /reset  /asr
/video/frame  /stickers  /profile  /moments
```

> 注：V0.2 之前 proxy 漏了 `/profile` 和 `/moments`，已补上。如果你拿到的是旧版 `vite.config.ts`，请确认这两条存在，否则 dev 下朋友圈会退回 mock、profile 不持久。

### 2.4 关键约束（务必遵守）

1. **`chat_db` / `chat.db` 是共享只读，绝对不要改**。朋友圈/幂等/profile 的数据用 ling 自有 SQLite（`backend/ling_data.db`，独立表 + 独立锁）。
2. 沿用统一错误信封（见 [§7](#7-错误码与统一信封规范)）。
3. `emotion` 枚举固定 5 值：`日常 / 调情 / 撒娇 / 焦急 / 冷淡`，**不要发明新值**（前端头像/表情包按这 5 个映射）。

---

## 3. V0.2 新增接口契约（重点）

> 以下接口前端在 `webview/src/api/backend.ts` 已封装。**返回字段名/结构必须与此处一致**，否则前端类型对不上。

### 3.1 朋友圈 Moments（7 个接口）

#### 数据结构

```ts
type Emotion = '日常' | '调情' | '撒娇' | '焦急' | '冷淡'

interface Moment {
  id: string                       // 唯一 ID
  author: '刘嘉玲' | '我'           // 谁发的
  content: string                  // 正文
  images?: string[]                // 图片 URL 或 base64（可选）
  ts: number                       // unix 秒（注意是秒，不是毫秒）
  source?: string                  // 来源标记，如 "来自朋友圈"（可选）
  likes: { name: string }[]        // 点赞人列表
  comments: MomentComment[]        // 评论列表
}

interface MomentComment {
  id: string
  name: string                     // 评论人："我" / "刘嘉玲" / 其他人
  text: string                     // 评论内容
  reply?: string                   // 她的 LLM 回复（仅"我"评论后后端生成）
  reply_emotion?: Emotion          // 回复情绪
  ts: number                       // unix 秒
}
```

---

#### ① `GET /moments` — 拉朋友圈列表（分页）

**Query**：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| limit | int | 否 | 每页条数，默认 20 |
| before | number | 否 | unix 秒，返回 `ts < before` 的动态（向下翻页） |

**返回 200**：
```json
{
  "items": [Moment, ...],
  "has_more": true
}
```
- `items` 按 `ts` **降序**（最新在前）
- `has_more` 表示是否还有更早的动态

**调用时机**：进朋友圈页拉最新 20 条（不带 before）；下拉刷新同样不带 before；上滑加载更多带 `before=最早一条的 ts`。

---

#### ② `POST /moments` — 我发朋友圈

**Body**：
```json
{
  "content": "这一刻的想法…",
  "images": ["data:image/png;base64,..."]
}
```
- `images` 可选，最多 9 张；现阶段前端发的是 `URL.createObjectURL` 的 blob URL 或 base64，**后端按实际存储方案定**（建议落盘存 URL，或直接存 base64）。

**返回 200**：
```json
{ "ok": true, "id": "m_xxx" }
```

**说明**：前端发完会重新拉列表（①），所以这条只要入库成功即可。

---

#### ③ `POST /moments/{id}/like` — 点赞 / 取消点赞（幂等切换）

**Path**：`id` = 朋友圈 ID

**Body**：
```json
{ "name": "我" }
```

**返回 200**：
```json
{
  "ok": true,
  "liked": true,     // 操作后状态：true=已赞，false=已取消
  "count": 3         // 操作后点赞总数
}
```

**说明**：幂等切换——已赞则取消，未赞则赞。前端做了**乐观更新**，后端返回最终状态用于校正。

---

#### ④ `POST /moments/{id}/comments` — 我评论（触发 LLM 生成她回复）

> ⚠️ 路径是 `/comments`（复数），不是 `/comment`。

**Path**：`id` = 朋友圈 ID

**Body**：
```json
{ "text": "厉害啊" }
```

**返回 200**：
```json
{
  "ok": true,
  "comment_id": "c_xxx",
  "reply": "那必须的 嘿嘿",       // 她的 LLM 回复（必填，非空）
  "reply_emotion": "调情"          // 回复情绪（5 选 1）
}
```

**说明**：这是朋友圈「聊天」的核心。后端收到评论后：
1. 存评论；
2. 调 LLM（基于 persona + 朋友圈正文 + 评论内容）生成她的短回复 + emotion；
3. **同步返回**回复（前端乐观加评论，收到 `reply` 后补到评论上）。

如果生成耗时较长（>5s），后续可改异步（前端先拿 `comment_id`，再轮询或 WS 推送 `reply`）。**现阶段同步即可**，前端有 30s 超时。

可复用 `core.py` 现有 LLM 调用 + emotion 解析逻辑（`_parse_emotion_reply`）。

---

#### ⑤ `GET /moments/new_count` — 红点未读数（轮询）

**Query**：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| since | number | 是 | unix 秒，返回 `ts > since` 的新动态数 |

**返回 200**：
```json
{ "count": 3 }
```

**说明**：前端在「发现」tab 每 30 秒轮询此接口（`since = 上次查看时间戳`），有新动态则朋友圈入口显示红点。用户进朋友圈页后前端清零（前端记 `last_seen`）。**只数她（author=刘嘉玲）发的新动态**，我自己的不算。

---

#### ⑥ `GET /moments/config` — 读取发圈频率配置

**返回 200**：
```json
{ "post_interval_sec": 300 }
```

**说明**：后端定时器每隔 `post_interval_sec` 秒选/生成一条朋友圈发出。前端「我」页展示当前值。

---

#### ⑦ `POST /moments/config` — 调整发圈频率

**Body**：
```json
{ "post_interval_sec": 60 }
```

**返回 200**：
```json
{ "ok": true }
```

**说明**：前端「我」页提供选项：`60`(1分钟·测试) / `300`(5分钟) / `1800`(30分钟) / `7200`(2小时) / `10800`(3小时·正式)。后端收到后**重置定时器**。

---

#### 朋友圈后端实现要点

**内容来源（混合方案）**：
1. **预设库优先**：维护 `moment_templates` 表（id, content, images, category），她发圈时随机选未用过的，可由你预填；
2. **LLM 兜底**：库空或用完时，调 LLM 基于 persona + `memory_meta.json` 真实对话素材生成新朋友圈（不重复），生成时带情绪标签。

**定时发圈**：后端启动后台线程/timer，按 `post_interval_sec` 间隔发圈；配置变更（⑦）后重置 timer；发圈时从模板库选或 LLM 生成，写入 moments 表。

**评论 LLM 回复**：构造 prompt —— system: persona（`SKILL_CORE.md`）；context: 朋友圈正文 + 我的评论；要求: 生成符合她语气的短回复 + emotion（5 选 1）。

---

### 3.2 个人资料 Profile（2 个接口）

> **后端已实现 ✅**（`api_server.py` + `profile.py`），前端已对接。**列在这里仅供你确认契约不要改。** 实测：`GET /profile` → `{"name":"刘嘉玲","signature":"在呢宝贝，怎么了","avatar":""}`。

`Profile` 结构：
```ts
interface Profile {
  name: string
  signature: string
  avatar: string   // base64 data URL；空串 = 用默认头像
}
```

#### `GET /profile`
返回 `Profile`。

#### `PUT /profile`
**Body**（只传要改的字段）：
```json
{ "name": "玲玲", "signature": "在呢", "avatar": "data:image/png;base64,..." }
```
返回：
```json
{ "ok": true, "profile": Profile }
```

V0.2 用法：「我」页顶部大头像卡展示 `name`/`avatar`；`ProfileEditor.vue` 编辑后 PUT 回写。`avatar` 为空时前端用默认 svg。

---

### 3.3 `/chat` 幂等增强（client_message_id）

> **后端已实现 ✅**（`idempotency.py`）。前端 V0.2 起每次发消息都带 `client_message_id`。**不要改契约。**

**请求**（`POST /chat`）：
```json
{
  "text": "想你了",
  "client_message_id": "lrxxx-xxxx"   // 前端生成，用于幂等去重
}
```

**正常返回**：
```json
{ "ok": true, "request_id": "...", "reply": "哟\n怎么想起我了", "emotion": "撒娇" }
```

**幂等命中返回**（同 `client_message_id` 重发）：
```json
{ "ok": true, "request_id": "...", "reply": "...", "emotion": "...", "idempotent": true }
```

行为：命中缓存直接返回首次结果，**不重调 LLM、不重复写历史**。`idempotent` 字段前端不依赖，但建议带上便于排查。空 `client_message_id` 直通（不缓存）。

---

### 3.4 新增错误码 CONTENT_BLOCKED

> **后端已实现 ✅**（`errors.py` 的 `classify_llm_error`）。前端已对接。**不要改。**

当上游 LLM 返回 422 / `input new_sensitive`（内容审核拦截）时，后端返回：

```json
{
  "ok": false,
  "request_id": "...",
  "error": {
    "code": "CONTENT_BLOCKED",
    "message": "...",
    "retryable": false
  }
}
```

前端特判：`CONTENT_BLOCKED` **不显示系统错误**，而是让刘嘉玲用自己口吻婉拒（`哎呀\n这个不想聊\n说点别的嘛`，emotion=撒娇），保持沉浸感。**关键：`retryable` 必须是 `false`**，否则前端会显示可点的重试徽章，用户重试同文本死循环。

---

## 4. 已有接口速查（V0.1，全通，保留）

这些接口 V0.2 仍在用，后端已实现且 live 验证通过。**列在这里仅供完整性，不要改契约。**

| 方法 | 路径 | 入参 | 出参 | 说明 |
|---|---|---|---|---|
| POST | `/chat` | `{text, client_message_id}` | `{ok, request_id, reply, emotion}` | 文字→LLM→回复+情绪（见 §3.3） |
| POST | `/chat/image` | `{text, image}` | `{reply, emotion, sticker}` | 图片+文字→VLM→回复+情绪+表情包 |
| POST | `/video/frame` | `{text, image}` | `{reply, emotion}` | 视频帧→VLM→回复 |
| POST | `/asr` | `{audio, sample_rate}` | `{text}` | base64 WAV→FunASR→文字（代理 8766） |
| GET | `/tts` | `?text=` | `audio/wav` | 文字→GPT-SoVITS→wav（代理 8880） |
| GET | `/stickers/{emotion}/{file}` | — | `image/png` | 表情包静态资源 |
| GET | `/health` | — | `{status, memory, db, user_id}` | 健康检查 |
| GET | `/history` | `?limit=30` | `[{role, content, ts}, ...]` | 最近对话（正序） |
| POST | `/reset` | — | `{ok: true}` | 清空对话历史 |

> ⚠️ **已知不一致**（V0.1 遗留，已 live 通，勿动）：`/chat/image`、`/video/frame` 成功响应**不带 `ok` 字段**，失败响应是 `{error: str}` 而非统一信封。前端已适配。新接口（moments/profile）请按 §7 统一信封来。

---

## 5. 待后端实现的功能（UI 已就绪）

下列功能前端 UI 已完成，接口到位即激活：

| 功能 | 前端入口 | 需要的接口 | 现状 |
|---|---|---|---|
| **朋友圈全部** | 发现 tab → 朋友圈 | §3.1 的 7 个 `/moments*` | 前端走 mock，**本文档要你实现的核心** |
| 按住说话录音 | 聊天 🎤 | 已有 `/asr`（需 ws_server:8766 起来） | 接口在，服务未常驻 |
| 语音转文字 | 语音消息长按 | 已有 `/asr` | 同上 |
| 真视频通话信令 | 聊天 + → 视频通话 | WS `:8766 /ws/voice` | 接口在，服务未常驻 |
| 图片上传给 AI | 聊天 + → 相册 | 已有 `/chat/image` | 接口在，依赖 VLM |

> 即：**本文档唯一需要你新写代码的就是 §3.1 的 7 个朋友圈接口 + 定时发圈线程 + 评论 LLM 回复**。其余要么已通，要么接口已就绪只差服务启动。

---

## 6. 数据库设计建议

复用 `backend/ling_data.db`（ling 自有 SQLite，独立表 + 独立锁）。**不要动 `chat_db.py` / `chat.db`**。参考现有 `idempotency.py` 的建表模式。

```sql
CREATE TABLE IF NOT EXISTS moments (
    id TEXT PRIMARY KEY,
    author TEXT NOT NULL,          -- '刘嘉玲' | '我'
    content TEXT NOT NULL,
    images TEXT,                   -- JSON array
    ts REAL NOT NULL,
    source TEXT
);
CREATE INDEX IF NOT EXISTS idx_moments_ts ON moments(ts);

CREATE TABLE IF NOT EXISTS moment_likes (
    moment_id TEXT NOT NULL,
    name TEXT NOT NULL,
    ts REAL NOT NULL,
    PRIMARY KEY (moment_id, name)
);

CREATE TABLE IF NOT EXISTS moment_comments (
    id TEXT PRIMARY KEY,
    moment_id TEXT NOT NULL,
    name TEXT NOT NULL,
    text TEXT NOT NULL,
    reply TEXT,
    reply_emotion TEXT,
    ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_comments_moment ON moment_comments(moment_id);

-- 可选：预设朋友圈模板库（混合方案用）
CREATE TABLE IF NOT EXISTS moment_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    images TEXT,                   -- JSON array
    category TEXT,
    used INTEGER DEFAULT 0         -- 0=未用，1=已用
);

-- 朋友圈配置（单行）
CREATE TABLE IF NOT EXISTS moments_config (
    key TEXT PRIMARY KEY,
    value TEXT
);
-- 初始：INSERT OR IGNORE INTO moments_config(key, value) VALUES ('post_interval_sec', '300');
```

> profile / idempotency 表后端已建好（`profile.py`、`idempotency.py`），无需重复建。

---

## 7. 错误码与统一信封规范

### 7.1 统一错误信封（所有新接口必须遵守）

HTTP 非 2xx 时返回：

```json
{
  "ok": false,
  "request_id": "req_xxx",
  "error": {
    "code": "ERROR_CODE",
    "message": "用户可读的中文消息",
    "retryable": true
  }
}
```

前端 `http()` 会把它抛成 `ApiRequestError{code, retryable, requestId}`，再用 `errorToZh()` 转中文气泡。

### 7.2 错误码对照表（前端已实现的码）

| code | 含义 | retryable | 前端展示 |
|---|---|---|---|
| `INVALID_INPUT` | 入参不合法（空文本/超长等） | false | 消息内容不合法 |
| `UPSTREAM_TIMEOUT` / `TIMEOUT` | 上游/请求超时 | true | 她那边反应慢了，稍等重试 |
| `UPSTREAM_RATE_LIMITED` | 上游限流（429） | true | 说太快啦，等几秒再发 |
| `UPSTREAM_UNAVAILABLE` | 上游不可用（5xx） | true | 她暂时不在线，待会再试 |
| `RESPONSE_INVALID` | 响应格式非法 | true | 她好像走神了，再说一遍 |
| `CONTENT_BLOCKED` | 内容审核拦截 | **false** | 特判：她婉拒（不显示系统错误，见 §3.4） |
| `NETWORK_ERROR` | 网络错误（连不上/断网） | true | 网络断了，检查一下 |
| `INTERNAL_ERROR` | 内部错误（兜底） | true | 出了点小问题，重试一下 |

> 朋友圈接口失败时前端会**降级到 mock**（不抛错给用户），但请尽量按上表返回正确错误码，便于排查。

### 7.3 成功信封

- `/chat` 系列：`{ok:true, request_id, reply, emotion}`
- `/moments` 列表：`{items, has_more}`（**不带 ok**，前端类型如此）
- `/moments` 发圈/点赞/评论/配置：`{ok:true, ...}`
- `/moments/new_count`：`{count}`（**不带 ok**）
- `/moments/config` GET：`{post_interval_sec}`（**不带 ok**）
- `/profile` GET：`Profile`（**不带 ok**）；PUT：`{ok:true, profile}`

> 即：列表类/读取类返回裸数据对象，操作类返回 `{ok:true, ...}`。前端类型已固定，照此实现。

---

## 8. 集成验收清单

实现完 7 个朋友圈接口后，按此自测（curl 直连 :8765）：

```bash
# 0. 健康检查
curl http://127.0.0.1:8765/health
# 期望 {"status":"ok","memory":true,"db":true,"user_id":16}

# 1. 改频率为 1 分钟（测试档）
curl -X POST http://127.0.0.1:8765/moments/config \
  -H "Content-Type: application/json" \
  -d '{"post_interval_sec":60}'
# 期望 {"ok":true}

# 2. 读频率
curl http://127.0.0.1:8765/moments/config
# 期望 {"post_interval_sec":60}

# 3. 等 60s，看她自动发圈（或手动插一条 author=刘嘉玲 的测）
curl 'http://127.0.0.1:8765/moments?limit=20'
# 期望 {"items":[...],"has_more":false}  items 含 author=刘嘉玲 的动态

# 4. 红点计数（since=0 应返回全部她发的条数）
curl 'http://127.0.0.1:8765/moments/new_count?since=0'
# 期望 {"count":N}

# 5. 我发一条朋友圈
curl -X POST http://127.0.0.1:8765/moments \
  -H "Content-Type: application/json" \
  -d '{"content":"测试发圈","images":[]}'
# 期望 {"ok":true,"id":"..."}

# 6. 点赞（用上一步她那条的 id）
curl -X POST http://127.0.0.1:8765/moments/<ID>/like \
  -H "Content-Type: application/json" -d '{"name":"我"}'
# 期望 {"ok":true,"liked":true,"count":1}
# 再调一次 → {"ok":true,"liked":false,"count":0}

# 7. 评论（触发 LLM 回复，可能几秒）
curl -X POST http://127.0.0.1:8765/moments/<ID>/comments \
  -H "Content-Type: application/json" -d '{"text":"厉害啊"}'
# 期望 {"ok":true,"comment_id":"...","reply":"那必须的 嘿嘿","reply_emotion":"调情"}
```

**前端联调**：起 `cd webview && pnpm dev`，打开 `http://localhost:5173`：
- [ ] 进「发现」→ 朋友圈，看到真列表（不再是 mock 的台球/烧烤/王者荣耀三条）
- [ ] 点赞/取消点赞，红心切换且总数正确
- [ ] 评论，几秒后她的回复出现在评论下方
- [ ] 顶部相机 → 发一条朋友圈，发完列表刷新出现
- [ ] 「我」页改发圈频率，刷新后值保持
- [ ] 退出朋友圈回「发现」，过一会儿（按配置间隔）朋友圈入口出红点

全部通过 = 朋友圈后端集成完成，前端无需任何改动。

---

## 附：关键文件索引

| 关注点 | 文件 |
|---|---|
| 前端接口封装（所有 HTTP + WS） | `webview/src/api/backend.ts` |
| 朋友圈 Pinia store | `webview/src/stores/moments.ts` |
| 朋友圈主页 / 发圈 / 卡片 | `webview/src/views/Moments.vue`、`ComposeMoment.vue`、`components/MomentCard.vue` |
| 发现 tab（红点轮询） | `webview/src/views/Discover.vue` |
| 我 tab（频率配置） | `webview/src/views/Me.vue` |
| 聊天 store（幂等/CONTENT_BLOCKED/TTS/ASR） | `webview/src/stores/chat.ts` |
| 后端入口（新接口加这里） | `backend/api_server.py` |
| 后端核心（LLM/emotion 解析复用） | `backend/core.py` |
| 幂等实现（建表模式参考） | `backend/idempotency.py` |
| profile 实现（建表模式参考） | `backend/profile.py` |
| 错误分类（CONTENT_BLOCKED） | `backend/errors.py` |
| 朋友圈契约（本文 §3.1 的原始版） | `webview/MOMENTS_API.md` |
| V0.1 全量快照（架构/测试/修复记录） | `PROJECT_SNAPSHOT.md` |

---

**一句话总结**：后端只需在 `api_server.py` 加 §3.1 的 7 个 `/moments*` 接口 + 一个定时发圈线程 + 评论触发的 LLM 回复，数据落 `ling_data.db`（§6 建表），错误按 §7 信封。其余接口 V0.2 已就绪勿动。实现后起 `pnpm dev` 联调，按 §8 清单验收。
