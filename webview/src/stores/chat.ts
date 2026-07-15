import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as api from '@/api/backend'
import type { Emotion, ErrorCode } from '@/api/backend'
import { ApiRequestError } from '@/api/backend'
import { errorToZh } from '@/api/backend'
import { TtsQueue } from '@/utils/ttsQueue'
import { useSettingsStore } from './settings'
import { useProfileStore } from './profile'

export interface Message {
  id: string
  role: 'user' | 'assistant' // user=我，assistant=刘嘉玲
  content: string
  emotion?: Emotion // 仅 assistant 有
  ts: number
  pending?: boolean // 发送中占位
  failed?: boolean // 发送失败
  errorCode?: ErrorCode // 失败错误码（供重试判断）
  errorRetryable?: boolean // 是否可重试
  image?: string // 本地图片预览 URL
  quote?: { sender: string; text: string } // 引用回复的原文预览
  audioUrl?: string // 语音消息 URL（assistant 的 TTS 可点播）
  audioPlayed?: boolean
  recalled?: boolean // 已撤回
  transcript?: string // 语音转文字结果（ASR）
  isSystem?: boolean // 系统提示行（拍一拍/撤回提示，居中灰字）
  sticker?: string // assistant 回复带的表情包 URL
  // 重试用的内部字段（不入库，刷新即丢）
  _retryText?: string
  _retryQuote?: Message | null
  _retryFromVoice?: boolean
  _clientMessageId?: string
}

export const useChatStore = defineStore('chat', () => {
  const messages = ref<Message[]>([])
  const loading = ref(false)
  const sending = ref(false)
  const error = ref<string | null>(null)
  // 当前刘嘉玲情绪（用于头像切换），取最后一条 assistant 消息
  const currentEmotion = ref<Emotion>('日常')
  // 未读计数：AI 回复时若用户不在聊天窗口则 +1，进聊天窗口清零
  const unread = ref(0)
  // 是否在聊天窗口内（App 层 onActivated/onDeactivated 控制）
  const inChat = ref(false)
  // 多选模式
  const selectMode = ref(false)
  const selectedIds = ref<Set<string>>(new Set())

  let audio: HTMLAudioElement | null = null

  // 流式文字聊天：AbortController 控制打断（abort 关 SSE fetch + 后端检测断连停推）
  let chatAbort: AbortController | null = null
  // 逐句 TTS 串行播放队列（流式收到的每句话合成 wav 后入队，clear() 即打断）
  const ttsQueue = new TtsQueue({
    isActive: () => true,
    onPlayStart: () => {},
    onPlayEnd: () => {},
  })

  /** 进入聊天窗口时恢复历史 */
  async function loadHistory() {
    loading.value = true
    error.value = null
    try {
      const list = await api.history(30)
      messages.value = list.map((it) => ({
        id: cryptoId(),
        role: (it.role === 'user' ? 'user' : 'assistant') as 'user' | 'assistant',
        content: it.content,
        emotion: it.role === 'assistant' ? inferEmotion(it.content) : undefined,
        ts: typeof it.ts === 'number' ? it.ts : Date.now(),
      }))
      refreshEmotion()
    } catch (e) {
      error.value = (e as Error).message
      // 历史拉取失败不阻塞，给条系统提示
      messages.value = [
        {
          id: cryptoId(),
          role: 'assistant',
          content: '（无法连接后端，请检查 :8765 是否启动）',
          emotion: '日常',
          ts: Date.now(),
        },
      ]
    } finally {
      loading.value = false
    }
  }

  /** 发送文本：push 用户气泡 → 调 /chat → push 刘嘉玲气泡 → 可选 TTS 播放
   *  quote: 引用回复的原文消息（可选） */
  /**
   * 发文本 → /chat → push 回复 → TTS。
   * @param fromVoice 这次输入是否来自语音识别（按住说话）。
   *                  true → 她的回复自动播语音（语音回语音）
   *                  false → 默认只回文字（语音条可点播），~15% 概率她也发条语音
   */
  async function send(text: string, quote?: Message | null, fromVoice = false) {
    const trimmed = text.trim()
    if (!trimmed) return
    // 流式中再发消息 → 打断当前轮（abort SSE + 清 TTS 队列），而非丢弃
    if (sending.value) {
      _abortCurrentTurn()
    }
    sending.value = true
    error.value = null

    const userMsg: Message = {
      id: cryptoId(),
      role: 'user',
      content: trimmed,
      ts: Date.now(),
      quote: quote
        ? { sender: quote.role === 'user' ? '我' : useProfileStore().name, text: quote.content.slice(0, 40) }
        : undefined,
    }
    messages.value.push(userMsg)

    // 占位气泡（发送中）
    const pendingMsg: Message = {
      id: cryptoId(),
      role: 'assistant',
      content: '',
      emotion: '日常',
      ts: Date.now(),
      pending: true,
      // 存原始文本供重试用
      _retryText: trimmed,
      _retryQuote: quote || null,
      _retryFromVoice: fromVoice,
      _clientMessageId: cryptoId(),
    }
    messages.value.push(pendingMsg)
    // 取响应式代理引用（push 后原始对象的修改可能不触发更新）
    const pending = messages.value[messages.value.length - 1]

    await _doChat(pending, trimmed, fromVoice)
    sending.value = false
  }

  /** 打断当前流式轮次：abort SSE fetch + 清 TTS 播放队列。保留已收到的部分文字。 */
  function _abortCurrentTurn() {
    chatAbort?.abort()
    chatAbort = null
    ttsQueue.clear()
    // 当前 pending 消息保留已收到的部分文字，去掉 pending 态
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'assistant' && last.pending) {
      last.pending = false
      if (!last.content) last.content = '（已打断）'
    }
    sending.value = false
  }

  /** 实际调 /chat/stream 流式填充 pending 消息。send 和 retry 共用。 */
  async function _doChat(pending: Message, text: string, fromVoice: boolean) {
    chatAbort = new AbortController()
    const settings = useSettingsStore()
    const shouldAutoPlay = settings.autoTts && (fromVoice || Math.random() < 0.15)
    try {
      await api.chatStream(
        text,
        pending._clientMessageId!,
        {
          onEmotion: (e) => {
            pending.emotion = e
            currentEmotion.value = e
          },
          onChunk: (sentence) => {
            // 边收边累加渲染；首句到达即去掉 pending 省略号
            pending.content += sentence
            pending.pending = false
            pending.failed = false
            pending.errorCode = undefined
            // 逐句触发 TTS（整句 wav 入队串行播放）
            if (shouldAutoPlay && sentence.trim()) {
              fetchTts(sentence)
                .then((url) => void ttsQueue.enqueueWavUrl(url))
                .catch((e) => console.warn('TTS 获取失败:', e))
            }
          },
          onDone: () => {
            pending.pending = false
            if (!pending.content) {
              pending.content = '（没有回复）'
              pending.failed = true
            } else if (!inChat.value) {
              unread.value++
            }
            // 整段回复的 audioUrl 用首句占位（点播时 playMessageAudio 会现取完整 TTS）
          },
          onError: (err) => {
            pending.content = err || '她好像走神了，再说一遍'
            pending.emotion = '冷淡'
            pending.pending = false
            pending.failed = true
            pending.errorCode = 'RESPONSE_INVALID'
            pending.errorRetryable = true
            error.value = pending.content
          },
        },
        chatAbort.signal,
      )
    } catch (e: unknown) {
      // 打断：AbortError 静默（_abortCurrentTurn 已处理 UI）
      if (e instanceof DOMException && e.name === 'AbortError') return
      const apiError = e instanceof ApiRequestError ? e : null
      const code = apiError?.code ?? 'INTERNAL_ERROR'
      const retryable = apiError?.retryable ?? true

      // CONTENT_BLOCKED：保持沉浸感，用她的口吻婉拒
      if (code === 'CONTENT_BLOCKED') {
        pending.content = '哎呀\n这个不想聊\n说点别的嘛'
        pending.emotion = '撒娇'
        pending.pending = false
        pending.failed = false
        currentEmotion.value = '撒娇'
        if (!inChat.value) unread.value++
        return
      }

      pending.content = apiError ? errorToZh(apiError) : '发送失败，请重试'
      pending.emotion = '冷淡'
      pending.pending = false
      pending.failed = true
      pending.errorCode = code
      pending.errorRetryable = retryable
      error.value = pending.content
    }
  }

  /** 重试一条失败的消息 */
  async function retry(msg: Message) {
    if (!msg._retryText || sending.value) return
    sending.value = true
    error.value = null
    msg.pending = true
    msg.failed = false
    msg.content = ''
    msg.errorCode = undefined
    await _doChat(msg, msg._retryText, msg._retryFromVoice || false)
    sending.value = false
  }

  /** 请求 /tts 拿 wav，返回可复用的 object URL（不自动播放） */
  async function fetchTts(text: string): Promise<string> {
    const blob = await api.tts(text)
    return URL.createObjectURL(blob)
  }

  /** 播放一个音频 URL（单例，播新停旧。不 revoke URL —— 消息里的 audioUrl 要复用） */
  function playUrl(url: string): Promise<void> {
    if (audio) {
      audio.pause()
      audio = null
    }
    audio = new Audio(url)
    return audio.play()
  }

  /** 点播某条 AI 消息的语音（无则现取 /tts） */
  async function playMessageAudio(msg: Message) {
    if (!msg.content) return
    let url = msg.audioUrl
    if (!url) {
      url = await fetchTts(msg.content)
      msg.audioUrl = url
    }
    msg.audioPlayed = true
    await playUrl(url)
  }

  function stopTts() {
    if (audio) {
      audio.pause()
      audio = null
    }
    ttsQueue.clear()
    // 停止流式请求（如果正在进行）
    chatAbort?.abort()
    chatAbort = null
  }

  /** 清空对话（调后端 /reset + 清本地） */
  async function reset() {
    await api.reset()
    // 释放所有消息持有的 Object URL
    messages.value.forEach(_revokeMsgUrls)
    messages.value = []
    currentEmotion.value = '日常'
    unread.value = 0
    exitSelect()
    stopTts()
  }

  function refreshEmotion() {
    for (let i = messages.value.length - 1; i >= 0; i--) {
      const m = messages.value[i]
      if (m.role === 'assistant' && m.emotion) {
        currentEmotion.value = m.emotion
        return
      }
    }
    currentEmotion.value = '日常'
  }

  // 历史记录里没有 emotion 字段，兜底用"日常"
  function inferEmotion(_content: string): Emotion {
    return '日常'
  }

  function cryptoId(): string {
    return Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
  }

  /** 释放消息持有的 Object URL（图片预览 + TTS 音频） */
  function _revokeMsgUrls(m: Message) {
    if (m.image && m.image.startsWith('blob:')) URL.revokeObjectURL(m.image)
    if (m.audioUrl && m.audioUrl.startsWith('blob:')) URL.revokeObjectURL(m.audioUrl)
  }

  /** 删除单条消息（长按菜单用） */
  function removeMessage(id: string) {
    const idx = messages.value.findIndex((m) => m.id === id)
    if (idx >= 0) {
      _revokeMsgUrls(messages.value[idx])
      messages.value.splice(idx, 1)
    }
  }

  /** 撤回消息（仅自己 2 分钟内发的） */
  function recallMessage(id: string) {
    const m = messages.value.find((x) => x.id === id)
    if (!m || m.role !== 'user') return
    if (Date.now() - m.ts > 2 * 60 * 1000) {
      pushSystem('超过 2 分钟的消息不能撤回')
      return
    }
    m.recalled = true
    m.content = ''
    m.image = undefined
    // 紧跟一条系统提示
    pushSystem('你撤回了一条消息')
  }

  /** 拍一拍（双击头像） */
  function pat(target: 'user' | 'assistant') {
    const name = useProfileStore().name
    pushSystem(target === 'user' ? '你拍了拍自己' : `你拍了拍${name}`)
  }

  /** 语音转文字（接后端 /asr）：传入音频 blob → 返回文字 */
  async function voiceToText(msg: Message): Promise<void> {
    if (msg.transcript !== undefined) return
    // voiceToText 用于已有语音消息转文字；按住说话的识别走 transcribeAudio
    msg.transcript = '（此消息无音频数据）'
  }

  /** 录音 blob → 16kHz WAV → 后端 ASR → 文字（按住说话用）。
   *  MediaRecorder 产出的是 audio/webm，后端 ASR 只吃 WAV/PCM，必须先转。 */
  async function transcribeAudio(blob: Blob): Promise<string> {
    const wavBase64 = await audioBlobToWavBase64(blob)
    const { text } = await api.asr(wavBase64)
    return text
  }

  /** 任意音频 blob → 16kHz 单声道 WAV → base64（不含 data: 前缀）。 */
  async function audioBlobToWavBase64(blob: Blob): Promise<string> {
    const arrayBuf = await blob.arrayBuffer()
    const ctx = new AudioContext()
    const audioBuf = await ctx.decodeAudioData(arrayBuf)
    ctx.close()
    const targetSr = 16000
    const src = audioBuf.getChannelData(0)
    let data: Float32Array
    if (audioBuf.sampleRate !== targetSr) {
      const ratio = audioBuf.sampleRate / targetSr
      const newLen = Math.round(src.length / ratio)
      data = new Float32Array(newLen)
      for (let i = 0; i < newLen; i++) data[i] = src[Math.floor(i * ratio)]
    } else {
      data = src
    }
    const pcm16 = new Int16Array(data.length)
    for (let i = 0; i < data.length; i++) {
      const s = Math.max(-1, Math.min(1, data[i]))
      pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff
    }
    // Int16 PCM → WAV ArrayBuffer
    const wav = new ArrayBuffer(44 + pcm16.length * 2)
    const view = new DataView(wav)
    const writeStr = (off: number, str: string) => {
      for (let i = 0; i < str.length; i++) view.setUint8(off + i, str.charCodeAt(i))
    }
    writeStr(0, 'RIFF')
    view.setUint32(4, 36 + pcm16.length * 2, true)
    writeStr(8, 'WAVE')
    writeStr(12, 'fmt ')
    view.setUint32(16, 16, true)
    view.setUint16(20, 1, true)
    view.setUint16(22, 1, true)
    view.setUint32(24, targetSr, true)
    view.setUint32(28, targetSr * 2, true)
    view.setUint16(32, 2, true)
    view.setUint16(34, 16, true)
    writeStr(36, 'data')
    view.setUint32(40, pcm16.length * 2, true)
    let off = 44
    for (let i = 0; i < pcm16.length; i++, off += 2) view.setInt16(off, pcm16[i], true)
    // ArrayBuffer → base64
    const bytes = new Uint8Array(wav)
    let binary = ''
    for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i])
    return btoa(binary)
  }

  /** 推一条系统提示消息（居中灰字） */
  function pushSystem(text: string) {
    messages.value.push({
      id: cryptoId(),
      role: 'user',
      content: text,
      ts: Date.now(),
      isSystem: true,
    })
  }

  // 多选
  function startSelect(id: string) {
    selectMode.value = true
    selectedIds.value = new Set([id])
  }
  function toggleSelect(id: string) {
    const s = new Set(selectedIds.value)
    if (s.has(id)) s.delete(id)
    else s.add(id)
    selectedIds.value = s
  }
  function exitSelect() {
    selectMode.value = false
    selectedIds.value = new Set()
  }
  function deleteSelected() {
    // 释放被删消息的 Object URL
    messages.value.forEach((m) => {
      if (selectedIds.value.has(m.id)) _revokeMsgUrls(m)
    })
    messages.value = messages.value.filter((m) => !selectedIds.value.has(m.id))
    exitSelect()
  }

  /** 进聊天窗口：标记在聊天内 + 清未读 */
  function enterChat() {
    inChat.value = true
    unread.value = 0
  }
  /** 离开聊天窗口 */
  function leaveChat() {
    inChat.value = false
  }

  /** 发送图片：本地预览 + 上传后端 VLM 理解 → 刘嘉玲回复（带表情包）。
   *  读 file 转 base64 调 /chat/image，后端 VLM 看图后用人格回复。 */
  async function sendImage(file: File, caption = '') {
    if (sending.value) return
    const url = URL.createObjectURL(file)
    messages.value.push({
      id: cryptoId(),
      role: 'user',
      content: caption,
      image: url,
      ts: Date.now(),
    })

    // 占位气泡
    const pendingMsg: Message = {
      id: cryptoId(),
      role: 'assistant',
      content: '',
      emotion: '日常',
      ts: Date.now(),
      pending: true,
    }
    messages.value.push(pendingMsg)
    const pending = messages.value[messages.value.length - 1]
    sending.value = true

    try {
      const base64 = await fileToBase64(file)
      const { reply, emotion, sticker } = await api.chatWithImage(caption, base64)
      pending.content = reply
      pending.emotion = emotion
      pending.sticker = sticker || undefined
      pending.pending = false
      currentEmotion.value = emotion
      if (!inChat.value) unread.value++

      // TTS：图片对话默认只回文字（语音条可点播），~15% 概率她也发条语音
      const settings = useSettingsStore()
      const shouldAutoPlay = settings.autoTts && Math.random() < 0.15
      if (reply) {
        fetchTts(reply)
          .then((u) => {
            pending.audioUrl = u
            if (shouldAutoPlay) playUrl(u)
          })
          .catch((e) => console.warn('TTS 获取失败:', e))
      }
    } catch (e: any) {
      pending.content = errorToZh(e) || '图片识别失败'
      pending.emotion = '冷淡'
      pending.pending = false
      pending.failed = true
      pending.errorCode = e?.code
      pending.errorRetryable = e?.retryable ?? true
    } finally {
      sending.value = false
    }
  }

  /** File → base64 字符串（不含 data: 前缀） */
  function fileToBase64(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => {
        const result = reader.result as string
        // 去掉 "data:image/xxx;base64," 前缀
        const base64 = result.split(',')[1] || ''
        resolve(base64)
      }
      reader.onerror = reject
      reader.readAsDataURL(file)
    })
  }

  return {
    messages,
    loading,
    sending,
    error,
    currentEmotion,
    unread,
    inChat,
    selectMode,
    selectedIds,
    loadHistory,
    send,
    sendImage,
    retry,
    playMessageAudio,
    stopTts,
    reset,
    removeMessage,
    recallMessage,
    pat,
    voiceToText,
    transcribeAudio,
    startSelect,
    toggleSelect,
    exitSelect,
    deleteSelected,
    enterChat,
    leaveChat,
  }
})
