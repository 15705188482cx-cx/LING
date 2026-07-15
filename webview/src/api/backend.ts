// 后端 API 封装 —— 对接 ling/backend FastAPI :8765
// 接口契约（以 backend/api_server.py 为准）：
//   POST /chat   {text, client_message_id}  -> {ok, request_id, reply, emotion} | {ok:false, error}
//   POST /chat/image  {text, image}         -> {ok, request_id, reply, emotion, sticker} | {ok:false, error}
//   GET  /tts    ?text=            -> audio/wav 字节流
//   GET  /health                  -> {status, memory, db, user_id}
//   GET  /history ?limit=30        -> [{role, content, ts}]
//   POST /reset                   -> {ok}
//
// dev 走 vite proxy（同源），prod/静态部署时 BASE 走绝对地址可配

const BASE = import.meta.env.VITE_API_BASE || ''

export type Emotion = '日常' | '调情' | '撒娇' | '焦急' | '冷淡'

// ---------- 统一错误类型 ----------

export type ErrorCode =
  | 'INVALID_INPUT'
  | 'UPSTREAM_TIMEOUT'
  | 'UPSTREAM_RATE_LIMITED'
  | 'UPSTREAM_UNAVAILABLE'
  | 'RESPONSE_INVALID'
  | 'CONTENT_BLOCKED'
  | 'INTERNAL_ERROR'
  | 'NETWORK_ERROR'
  | 'TIMEOUT'

export interface ApiError {
  code: ErrorCode
  message: string
  retryable: boolean
  requestId?: string
}

/** 把 ApiError 转成用户可读的中文提示 */
export function errorToZh(err: ApiError): string {
  switch (err.code) {
    case 'INVALID_INPUT': return '消息内容不合法'
    case 'UPSTREAM_TIMEOUT':
    case 'TIMEOUT': return '她那边反应慢了，稍等重试'
    case 'UPSTREAM_RATE_LIMITED': return '说太快啦，等几秒再发'
    case 'UPSTREAM_UNAVAILABLE': return '她暂时不在线，待会再试'
    case 'RESPONSE_INVALID': return '她好像走神了，再说一遍'
    case 'CONTENT_BLOCKED': return '她不想聊这个，换个说法吧'
    case 'NETWORK_ERROR': return '网络断了，检查一下'
    case 'INTERNAL_ERROR':
    default: return '出了点小问题，重试一下'
  }
}

export class ApiRequestError extends Error {
  code: ErrorCode
  retryable: boolean
  requestId?: string
  constructor(e: ApiError) {
    super(e.message)
    this.code = e.code
    this.retryable = e.retryable
    this.requestId = e.requestId
  }
}

interface ErrorEnvelope {
  ok: false
  request_id?: string
  error: {
    code?: ErrorCode
    message?: string
    retryable?: boolean
  }
}

function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  if (!value || typeof value !== 'object') return false
  const candidate = value as { ok?: unknown; error?: unknown }
  return candidate.ok === false && typeof candidate.error === 'object' && candidate.error !== null
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

// ---------- 通用 HTTP ----------

const DEFAULT_TIMEOUT = 30000 // 30 秒

interface HttpOptions extends RequestInit {
  timeout?: number
}

async function http<T>(url: string, init?: HttpOptions): Promise<T> {
  const { timeout = DEFAULT_TIMEOUT, ...rest } = init || {}
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)
  try {
    const res = await fetch(BASE + url, { ...rest, signal: controller.signal })
    if (!res.ok) {
      // 尝试解析统一错误格式
      let body: unknown = null
      try { body = await res.json() } catch { /* 非 JSON */ }
      if (isErrorEnvelope(body)) {
        throw new ApiRequestError({
          code: body.error.code ?? 'INTERNAL_ERROR',
          message: body.error.message || '请求失败',
          retryable: body.error.retryable ?? false,
          requestId: body.request_id,
        })
      }
      // 非 JSON 或旧格式错误
      const text = await res.text().catch(() => '')
      throw new ApiRequestError({
        code: res.status >= 500 ? 'UPSTREAM_UNAVAILABLE' : 'INTERNAL_ERROR',
        message: `${res.status} ${res.statusText} ${text}`.trim(),
        retryable: res.status >= 500 || res.status === 429,
      })
    }
    return res.json() as Promise<T>
  } catch (e: unknown) {
    if (e instanceof ApiRequestError) throw e
    if (isAbortError(e)) {
      throw new ApiRequestError({
        code: 'TIMEOUT',
        message: '请求超时',
        retryable: true,
      })
    }
    // 网络错误（连不上、断网）
    throw new ApiRequestError({
      code: 'NETWORK_ERROR',
      message: errorMessage(e, '网络错误'),
      retryable: true,
    })
  } finally {
    clearTimeout(timer)
  }
}

/** 生成 client_message_id（用于幂等去重） */
function genClientMsgId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
}

export interface ChatResponse {
  ok: true
  request_id: string
  reply: string
  emotion: Emotion
}

export interface HistoryItem {
  role: 'user' | 'assistant' | string
  content: string
  ts?: string | number
}

export interface HealthResponse {
  status: string
  memory: boolean
  db: boolean
  user_id: number | string
}

/** 发文本，拿回复 + 情绪 */
export function chat(text: string, clientMessageId = genClientMsgId()): Promise<ChatResponse> {
  return http<ChatResponse>('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, client_message_id: clientMessageId }),
  })
}

// ---------- 流式文字聊天（SSE） ----------

/** 流式聊天回调：逐句文字 + 情绪 + 结束/出错 */
export interface ChatStreamCallbacks {
  /** 初始情绪（首句前）和最终情绪（流结束前）各触发一次 */
  onEmotion?: (emotion: Emotion) => void
  /** 逐句文字（前端累加渲染 + 触发该句 TTS） */
  onChunk?: (sentence: string) => void
  /** 流正常结束 */
  onDone?: () => void
  /** 出错（非打断） */
  onError?: (err: string) => void
}

/**
 * 流式文字聊天：POST /chat/stream，用 fetch + ReadableStream 解析 SSE。
 * 不经过 http()（它会 res.json() 一次性解析，无法流式）。
 * signal 由外部传入，abort() 即打断（关闭 fetch 流，后端检测断连停止推送）。
 */
export async function chatStream(
  text: string,
  clientMessageId: string,
  cb: ChatStreamCallbacks,
  signal: AbortSignal,
): Promise<void> {
  const res = await fetch(BASE + '/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, client_message_id: clientMessageId }),
    signal,
  })
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`
    try { msg = (await res.json())?.error?.message || msg } catch { /* 非 JSON */ }
    throw new ApiRequestError({
      code: res.status >= 500 ? 'UPSTREAM_UNAVAILABLE' : 'INTERNAL_ERROR',
      message: msg,
      retryable: res.status >= 500,
    })
  }
  if (!res.body) throw new ApiRequestError({ code: 'INTERNAL_ERROR', message: '无响应流', retryable: false })

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  let currentEvent = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      // SSE 按空行分隔事件，每行 "field: value"
      const lines = buf.split('\n')
      buf = lines.pop() ?? '' // 最后一行可能不完整，留着
      for (const line of lines) {
        if (line.startsWith('event:')) {
          currentEvent = line.slice(6).trim()
        } else if (line.startsWith('data:')) {
          const data = line.slice(5).trim()
          switch (currentEvent) {
            case 'emotion': cb.onEmotion?.(data as Emotion); break
            case 'chunk': cb.onChunk?.(data); break
            case 'done': cb.onDone?.(); return
            case 'error': cb.onError?.(data); return
          }
          currentEvent = ''
        }
      }
    }
    // 流自然结束（没收到 done 事件）
    cb.onDone?.()
  } finally {
    reader.releaseLock()
  }
}

/** 文字转语音，返回 wav blob（可直接 new Audio(URL.createObjectURL(blob))） */
export async function tts(text: string): Promise<Blob> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 60000) // TTS 合成慢，给 60s
  try {
    const res = await fetch(BASE + '/tts?text=' + encodeURIComponent(text), { signal: controller.signal })
    if (!res.ok) {
      throw new ApiRequestError({
        code: res.status >= 500 ? 'UPSTREAM_UNAVAILABLE' : 'INTERNAL_ERROR',
        message: `语音合成失败 ${res.status}`,
        retryable: res.status >= 500,
      })
    }
    return res.blob()
  } catch (e: unknown) {
    if (e instanceof ApiRequestError) throw e
    if (isAbortError(e)) {
      throw new ApiRequestError({ code: 'TIMEOUT', message: '语音合成超时', retryable: true })
    }
    throw new ApiRequestError({ code: 'NETWORK_ERROR', message: '网络错误', retryable: true })
  } finally {
    clearTimeout(timer)
  }
}

/** 健康检查 + 资源就绪状态 */
export function health(): Promise<HealthResponse> {
  return http<HealthResponse>('/health')
}

/** 最近 limit 条对话（正序） */
export function history(limit = 30): Promise<HistoryItem[]> {
  return http<HistoryItem[]>(`/history?limit=${limit}`)
}

/** 清空对话历史 */
export function reset(): Promise<{ ok: boolean }> {
  return http<{ ok: boolean }>('/reset', { method: 'POST' })
}

// ---------- 个人资料（名字/头像/签名） ----------

export interface Profile {
  name: string
  signature: string
  avatar: string  // base64 data URL；空 = 用默认头像
}

/** 读取个人资料 */
export function getProfile(): Promise<Profile> {
  return http<Profile>('/profile')
}

/** 更新个人资料（只传要改的字段） */
export function updateProfile(partial: Partial<Profile>): Promise<{ ok: boolean; profile: Profile }> {
  return http<{ ok: boolean; profile: Profile }>('/profile', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(partial),
  })
}

// ---------- 图片/视频/ASR 接口（批1-3 新增） ----------

export interface ChatImageResponse {
  reply: string
  emotion: Emotion
  sticker?: string  // 表情包 URL（如 /stickers/撒娇/撒娇.png），空则无
}

/** 带图对话：图片+文字 → VLM理解 → {reply, emotion, sticker} */
export function chatWithImage(text: string, imageBase64: string): Promise<ChatImageResponse> {
  return http<ChatImageResponse>('/chat/image', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, image: imageBase64 }),
  })
}

/** 视频帧对话：摄像头帧+文字 → VLM看一眼 → {reply, emotion} */
export function videoFrame(text: string, imageBase64: string): Promise<{ reply: string; emotion: Emotion }> {
  return http<{ reply: string; emotion: Emotion }>('/video/frame', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, image: imageBase64 }),
  })
}

/** 语音转文字（按住说话）：base64 WAV → {text} */
export function asr(audioBase64: string, sampleRate = 16000): Promise<{ text: string }> {
  return http<{ text: string }>('/asr', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ audio: audioBase64, sample_rate: sampleRate }),
  })
}

/** 拼接表情包完整 URL（dev 走 proxy，prod 走 BASE） */
export function stickerUrl(path: string): string {
  return BASE + path
}

// ---------- WebSocket 语音/视频通话客户端 ----------

/** 通话模式：auto=服务端 VAD 自动断句，manual=前端 start/stop 控制 */
export type CallMode = 'auto' | 'manual'

/** WS 通话回调接口（V0.3：tts_stop 替代 tts_end，支持打断） */
export interface VoiceCallCallbacks {
  onReady?: () => void
  onAsrText?: (text: string) => void
  onLlmChunk?: (text: string) => void
  onEmotion?: (emotion: Emotion) => void
  onTtsStart?: () => void
  /** V0.3：收到 TTS 音频包（Opus 二进制，60ms/包，边收边播） */
  onTtsAudio?: (opusBytes: ArrayBuffer) => void
  /** V0.3：TTS 停止（正常结束或被打断），前端应清播放队列 */
  onTtsStop?: (reason?: string) => void
  onDone?: (reason?: string) => void
  onError?: (err: string) => void
}

/**
 * 语音/视频通话 WS 客户端，对接 backend/ws_server.py :8766（V0.3）。
 *
 * V0.3 协议：
 *   connect() → hello(mode='auto') → 收 ready → 持续 sendAudio(Opus 包)
 *   服务端 VAD 自动断句，无需手动 start/stop
 *   收到 tts_stop → 清播放队列（被打断或说完）
 *   abort() → 打断她的 TTS
 *
 * 用法（auto 模式）：
 *   const call = new VoiceCallClient(callbacks)
 *   await call.connect()
 *   call.hello('auto', 16000)    // 握手，声明 auto 模式
 *   call.sendAudio(opusPacket)   // 持续发 Opus 包（录音回调里调）
 *   call.abort()                 // 打断她
 *   call.sendVideoFrame(b64)     // 视频模式
 *   call.close()                 // 挂断
 */
export class VoiceCallClient {
  private ws: WebSocket | null = null
  private cb: VoiceCallCallbacks
  private url: string

  constructor(cb: VoiceCallCallbacks) {
    this.cb = cb
    const wsBase = import.meta.env.VITE_WS_URL || 'ws://127.0.0.1:8766'
    this.url = wsBase.endsWith('/ws/voice') ? wsBase : wsBase.replace(/\/$/, '') + '/ws/voice'
  }

  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(this.url)
      this.ws.binaryType = 'arraybuffer'
      this.ws.onopen = () => resolve()
      this.ws.onmessage = (ev) => this.onMessage(ev)
      this.ws.onerror = () => {
        this.cb.onError?.('WS 连接失败')
        reject(new Error('WS connect failed'))
      }
      this.ws.onclose = () => this.cb.onDone?.('closed')
    })
  }

  private onMessage(ev: MessageEvent) {
    // 二进制 = TTS Opus 音频包（60ms/包）
    if (ev.data instanceof ArrayBuffer) {
      this.cb.onTtsAudio?.(ev.data)
      return
    }
    // JSON 控制帧
    try {
      const d = JSON.parse(ev.data as string)
      switch (d.type) {
        case 'ready': this.cb.onReady?.(); break
        case 'asr_text': this.cb.onAsrText?.(d.text); break
        case 'llm_chunk': this.cb.onLlmChunk?.(d.text); break
        case 'emotion': this.cb.onEmotion?.(d.emotion as Emotion); break
        case 'tts_start': this.cb.onTtsStart?.(); break
        // V0.3：tts_stop 替代旧的 tts_end（支持打断通知）
        case 'tts_stop': this.cb.onTtsStop?.(d.reason); break
        case 'tts_end': this.cb.onTtsStop?.(); break // 兼容旧后端
        case 'done': this.cb.onDone?.(d.reason); break
      }
    } catch {
      // 忽略非 JSON
    }
  }

  private send(obj: object) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(obj))
    }
  }

  /** V0.3 握手：声明模式 + 采样率。connect 后立即调 */
  hello(mode: CallMode = 'auto', sampleRate = 16000) {
    this.send({ type: 'hello', mode, sample_rate: sampleRate })
  }

  /** manual 模式：开始录音（auto 模式不需要） */
  start(sampleRate: number) {
    this.send({ type: 'start', sample_rate: sampleRate })
  }

  /** 发音频块（二进制 Opus 包） */
  sendAudio(bytes: ArrayBuffer | Blob) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(bytes)
    }
  }

  /** manual 模式：说完一句触发处理（auto 模式不需要，VAD 自动触发） */
  stop(sampleRate: number) {
    this.send({ type: 'stop', sample_rate: sampleRate })
  }

  /** 打断她的 TTS（V0.3：服务端清队列 + 通知前端停播） */
  abort() {
    this.send({ type: 'abort' })
  }

  /** 视频模式：推送摄像头帧（base64，不含 data: 前缀） */
  sendVideoFrame(imageBase64: string) {
    this.send({ type: 'video_frame', image: imageBase64 })
  }

  /** 挂断 */
  close() {
    this.ws?.close()
    this.ws = null
  }
}

// ---------- 朋友圈（Moments）接口 ----------
// 契约见 MOMENTS_API.md。后端未实现时各函数走 mock 兜底，界面可独立验收。

export interface MomentComment {
  id: string
  name: string        // 评论人："我" / "刘嘉玲"
  text: string
  reply?: string      // 她的 LLM 回复（仅我评论后后端生成）
  reply_emotion?: Emotion
  ts: number
}

export interface Moment {
  id: string
  author: '刘嘉玲' | '我'
  content: string
  images?: string[]
  ts: number
  source?: string
  likes: { name: string }[]
  comments: MomentComment[]
}

export interface MomentsListResponse {
  items: Moment[]
  has_more: boolean
}

export interface NewCountResponse {
  count: number
}

export interface MomentsConfig {
  post_interval_sec: number
}

// ---- mock 数据（后端未实现时兜底）----
const MOCK_ME = { name: '我' }
let mockLikedIds = new Set<string>()

const MOCK_MOMENTS: Moment[] = [
  {
    id: 'm1',
    author: '刘嘉玲',
    content: '今天台球又赢了三局 哼哼',
    images: [],
    ts: Date.now() / 1000 - 3600,
    source: '来自朋友圈',
    likes: [{ name: '我' }],
    comments: [
      { id: 'c1', name: '我', text: '厉害啊', reply: '那必须的 嘿嘿', reply_emotion: '调情', ts: Date.now() / 1000 - 3500 },
    ],
  },
  {
    id: 'm2',
    author: '刘嘉玲',
    content: '深夜放毒 烧烤真香',
    images: [],
    ts: Date.now() / 1000 - 7200,
    source: '来自朋友圈',
    likes: [],
    comments: [],
  },
  {
    id: 'm3',
    author: '刘嘉玲',
    content: '王者荣耀连跪五把 心态崩了',
    images: [],
    ts: Date.now() / 1000 - 10800,
    source: '来自朋友圈',
    likes: [{ name: '王丽' }],
    comments: [
      { id: 'c2', name: '王丽', text: '哈哈哈哈活该', ts: Date.now() / 1000 - 10700 },
    ],
  },
]

function mockMomentsList(limit: number, before?: number): MomentsListResponse {
  let items = [...MOCK_MOMENTS]
  if (before) items = items.filter((m) => m.ts < before)
  items.sort((a, b) => b.ts - a.ts)
  const sliced = items.slice(0, limit)
  return { items: sliced, has_more: items.length > limit }
}

const MOCK_REPLIES = ['哈哈', '说得对', '讨厌啦', '嗯嗯', '你也是', '嘿嘿', '才不要', '好吧']
function mockReply(): { reply: string; reply_emotion: Emotion } {
  const reply = MOCK_REPLIES[Math.floor(Math.random() * MOCK_REPLIES.length)]
  const emotions: Emotion[] = ['日常', '调情', '撒娇', '焦急', '冷淡']
  return { reply, reply_emotion: emotions[Math.floor(Math.random() * emotions.length)] }
}

// ---- 对外接口（真接口优先，失败回退 mock）----

/** 拉朋友圈列表（分页） */
export async function getMoments(limit = 20, before?: number): Promise<MomentsListResponse> {
  try {
    const q = `?limit=${limit}` + (before ? `&before=${before}` : '')
    return await http<MomentsListResponse>(`/moments${q}`)
  } catch {
    return mockMomentsList(limit, before)
  }
}

/** 我发朋友圈 */
export async function postMoment(content: string, images: string[] = []): Promise<{ ok: boolean; id: string }> {
  try {
    return await http<{ ok: boolean; id: string }>('/moments', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content, images }),
    })
  } catch {
    // mock：本地插一条
    const id = 'local_' + Date.now()
    MOCK_MOMENTS.unshift({
      id,
      author: '我',
      content,
      images,
      ts: Date.now() / 1000,
      likes: [],
      comments: [],
    })
    return { ok: true, id }
  }
}

/** 点赞 / 取消点赞 */
export async function toggleLike(momentId: string, name = '我'): Promise<{ ok: boolean; liked: boolean; count: number }> {
  try {
    return await http<{ ok: boolean; liked: boolean; count: number }>(`/moments/${momentId}/like`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
  } catch {
    const m = MOCK_MOMENTS.find((x) => x.id === momentId)
    if (m) {
      const idx = m.likes.findIndex((l) => l.name === MOCK_ME.name)
      if (idx >= 0) {
        m.likes.splice(idx, 1)
        mockLikedIds.delete(momentId)
      } else {
        m.likes.push({ name: MOCK_ME.name })
        mockLikedIds.add(momentId)
      }
      return { ok: true, liked: mockLikedIds.has(momentId), count: m.likes.length }
    }
    return { ok: false, liked: false, count: 0 }
  }
}

/** 我评论；后端触发 LLM 生成她的回复 */
export async function postComment(
  momentId: string,
  text: string,
): Promise<{ ok: boolean; comment_id: string; reply?: string; reply_emotion?: Emotion }> {
  try {
    return await http<{ ok: boolean; comment_id: string; reply?: string; reply_emotion?: Emotion }>(
      `/moments/${momentId}/comments`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      },
    )
  } catch {
    // mock：本地加评论 + 假回复
    const m = MOCK_MOMENTS.find((x) => x.id === momentId)
    const { reply, reply_emotion } = mockReply()
    if (m) {
      m.comments.push({
        id: 'local_c_' + Date.now(),
        name: '我',
        text,
        reply,
        reply_emotion,
        ts: Date.now() / 1000,
      })
    }
    return { ok: true, comment_id: 'local_c_' + Date.now(), reply, reply_emotion }
  }
}

/** 红点未读数（自 since 起新动态数） */
export async function getNewCount(since: number): Promise<NewCountResponse> {
  try {
    return await http<NewCountResponse>(`/moments/new_count?since=${since}`)
  } catch {
    const count = MOCK_MOMENTS.filter((m) => m.ts > since && m.author === '刘嘉玲').length
    return { count }
  }
}

/** 读取发圈频率配置 */
export async function getMomentsConfig(): Promise<MomentsConfig> {
  try {
    return await http<MomentsConfig>('/moments/config')
  } catch {
    return { post_interval_sec: 300 } // mock 默认 5 分钟
  }
}

/** 调整发圈频率 */
export async function setMomentsConfig(post_interval_sec: number): Promise<{ ok: boolean }> {
  try {
    return await http<{ ok: boolean }>('/moments/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ post_interval_sec }),
    })
  } catch {
    return { ok: true } // mock 静默成功
  }
}
