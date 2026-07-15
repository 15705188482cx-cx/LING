# 朋友圈（Moments）接口契约

> 前端已实现，后端照此契约实现即可。前端在接口不可用时走 mock 兜底，后端实现后自动切真接口（无需改前端）。
>
> 所有接口挂在现有 FastAPI `:8765`，前端 dev proxy 已覆盖根路径。沿用现有统一错误信封 `{ok:false, request_id, error:{code,message,retryable}}`。

## 数据结构

```ts
type Emotion = '日常' | '调情' | '撒娇' | '焦急' | '冷淡'

interface Moment {
  id: string                      // 唯一 ID
  author: '刘嘉玲' | '我'          // 谁发的
  content: string                 // 正文
  images?: string[]               // 图片 URL 或 base64（可选）
  ts: number                      // unix 秒
  source?: string                 // 来源标记，如 "来自朋友圈"（可选）
  likes: { name: string }[]       // 点赞人列表
  comments: MomentComment[]       // 评论列表
}

interface MomentComment {
  id: string
  name: string                    // 评论人："我" / "刘嘉玲" / 其他人
  text: string                    // 评论内容
  reply?: string                  // 她的 LLM 回复（仅"我"评论后后端生成）
  reply_emotion?: Emotion         // 回复情绪
  ts: number
}
```

## 接口列表

### 1. GET `/moments` — 拉朋友圈列表（分页）

**Query**：
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| limit | int | 否 | 每页条数，默认 20 |
| before | number | 否 | unix 秒，返回 ts < before 的动态（向下翻页） |

**返回 200**：
```json
{
  "items": [Moment, ...],
  "has_more": true
}
```
- `items` 按 ts 降序（最新在前）
- `has_more` 表示是否还有更早的动态

**说明**：前端进朋友圈页时调此接口拉最新 20 条；下拉刷新同样调此接口（不带 before）；上滑加载更多带 before=最早一条的 ts。

---

### 2. POST `/moments` — 我发朋友圈

**Body**：
```json
{
  "content": "这一刻的想法…",
  "images": ["data:image/png;base64,...", ...]   // 可选，最多 9 张
}
```

**返回 200**：
```json
{ "ok": true, "id": "m_xxx" }
```

**说明**：前端发完会重新拉列表。图片现阶段可存 object URL 或 base64，后端按实际存储方案定。

---

### 3. POST `/moments/{id}/like` — 点赞 / 取消点赞

**Path**：`id` = 朋友圈 ID

**Body**：
```json
{ "name": "我" }
```

**返回 200**：
```json
{
  "ok": true,
  "liked": true,      // 操作后状态：true=已赞，false=已取消
  "count": 3          // 操作后点赞总数
}
```

**说明**：幂等切换——已赞则取消，未赞则赞。前端做了乐观更新，后端返回最终状态用于校正。

---

### 4. POST `/moments/{id}/comments` — 我评论（触发 LLM 生成她回复）

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
  "reply_emotion": "调情"          // 回复情绪
}
```

**说明**：这是朋友圈"聊天"的核心。后端收到评论后：
1. 存评论
2. 调 LLM（基于 persona + 朋友圈正文 + 评论内容）生成她的回复 + emotion
3. 同步返回回复（前端乐观加评论，收到 reply 后补到评论上）

如果后端生成回复耗时较长（>5s），可考虑后续改为异步——前端先拿 comment_id，再轮询或 WS 推送 reply。现阶段同步即可。

---

### 5. GET `/moments/new_count` — 红点未读数

**Query**：
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| since | number | 是 | unix 秒，返回 ts > since 的新动态数 |

**返回 200**：
```json
{ "count": 3 }
```

**说明**：前端在"发现"tab 每 30 秒轮询此接口（since = 上次查看时间戳），有新动态则朋友圈入口显示红点。用户进朋友圈页后清零（前端记 last_seen）。

---

### 6. GET `/moments/config` — 读取发圈频率配置

**返回 200**：
```json
{ "post_interval_sec": 300 }
```

**说明**：后端定时器每隔 `post_interval_sec` 秒选/生成一条朋友圈发出。前端"我"页展示当前值。

---

### 7. POST `/moments/config` — 调整发圈频率

**Body**：
```json
{ "post_interval_sec": 60 }
```

**返回 200**：
```json
{ "ok": true }
```

**说明**：前端"我"页提供选项：1 分钟（测试）/ 5 分钟 / 30 分钟 / 2 小时 / 3 小时（正式）。后端收到后重置定时器。

---

## 后端实现要点（给后端的建议）

### 内容来源（混合方案）
1. **预设库优先**：维护一张 `moment_templates` 表（id, content, images, category），她发圈时从中随机选未用过的。可由你预填。
2. **LLM 兜底生成**：库空或用完时，调 LLM 基于 persona + memory_meta.json 真实对话素材生成新朋友圈（不重复）。生成时带情绪标签。

### 数据存储
- 复用 ling 自有 SQLite（`ling_data.db`），独立表 + 独立锁，**不要动 `chat_db.py`/`chat.db`**（共享只读）。
- 建表参考（`idempotency.py` 模式）：
```sql
CREATE TABLE IF NOT EXISTS moments (
    id TEXT PRIMARY KEY,
    author TEXT NOT NULL,          -- '刘嘉玲' | '我'
    content TEXT NOT NULL,
    images TEXT,                   -- JSON array
    ts REAL NOT NULL,
    source TEXT
);
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
CREATE INDEX IF NOT EXISTS idx_moments_ts ON moments(ts);
```

### 定时发圈
- 后端启动一个后台线程/timer，按 `post_interval_sec` 间隔发圈。
- 配置变更（POST /moments/config）后重置 timer。
- 发圈时从模板库选或 LLM 生成，写入 moments 表。

### 评论 LLM 回复
- POST /moments/{id}/comments 收到后，构造 prompt：
  - system: persona（SKILL_CORE.md）
  - context: 朋友圈正文 + 我的评论
  - 要求: 生成符合她语气的短回复 + emotion（5 选 1）
- 可复用现有 `core.py` 的 LLM 调用 + emotion 解析逻辑。

---

## 前端实现状态

| 功能 | 状态 | 说明 |
|---|---|---|
| 发现 tab（入口+红点轮询） | ✅ | n02 真·微信图标 |
| 朋友圈主页（封面+列表+下拉刷新） | ✅ | |
| 单条卡片（正文/图片/点赞/评论） | ✅ | MomentCard.vue |
| 点赞（乐观更新） | ✅ | |
| 评论（乐观加+补回复） | ✅ | mock 模式假回复 |
| 发圈（文本+配图） | ✅ | |
| 发圈频率设置 | ✅ | "我"页 ActionSheet |
| 红点未读轮询 | ✅ | 30s 一次 |
| mock 兜底 | ✅ | 接口失败时本地数据跑通界面 |

前端在 `feat/moments` 分支，`pnpm build` 通过。后端实现上述 7 个接口后，前端自动切真接口（mock 仅在请求失败时触发）。
