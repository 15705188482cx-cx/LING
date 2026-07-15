// 串行 TTS 播放队列（V0.3：支持 Opus 包流式播放 + WAV 回退）
//
// V0.3 改造：
// - 后端逐个发 60ms Opus 包（不再整句 WAV），前端用 opus-decoder 解码
// - enqueueOpus(opusBytes) 收一个包解码一个，累积成 AudioBuffer 播放
// - 一句话的包用 sentenceStart/sentenceEnd 划分，句间无缝拼接
// - clear() 立即停播 + 清队列（打断/挂断用）
// - 兼容旧 WAV 模式：enqueueWav(wavBytes) 仍可用
//
// 设计：每句 Opus 包解码后拼成一个完整 AudioBuffer 再播（比逐包播更稳），
// 句间靠 onended 串行（不会重叠）。首句延迟 = 第一个 Opus 包解码时间（<10ms）。

import { OpusDecoder as WebOpusDecoder } from 'opus-decoder'

export interface TtsQueueOptions {
  /** 队列消费前置条件：返回 false 时不播放（如通话已结束） */
  isActive?: () => boolean
  /** 单句播放开始/结束回调（驱动 UI 的"正在说话"状态） */
  onPlayStart?: () => void
  onPlayEnd?: () => void
}

export class TtsQueue {
  // 当前句的 Opus 包累积（解码成 Float32 PCM 后拼）
  private currentPcm: Float32Array[] = []
  private currentSampleRate = 16000
  // 待播放的完整句子队列（每句是一个解码好的 AudioBuffer 数据）
  private queue: { pcm: Float32Array; sampleRate: number }[] = []
  private playing = false
  private ctx: AudioContext | null = null
  private gain: GainNode | null = null
  private source: AudioBufferSourceNode | null = null
  private speakerOn = true
  private opts: TtsQueueOptions
  // opus-decoder 的泛型在外部库，这里用已实例化类型。sampleRate=16000 在构造时指定
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private opusDecoder: any = null

  constructor(opts: TtsQueueOptions = {}) {
    this.opts = opts
  }

  /** 确保上下文就绪（懒初始化，需在用户交互后调） */
  private ensureCtx(): void {
    if (!this.ctx) this.ctx = new AudioContext()
    if (!this.gain) {
      this.gain = this.ctx.createGain()
      this.gain.connect(this.ctx.destination)
    }
    this.gain.gain.value = this.speakerOn ? 1 : 0
  }

  /** 确保解码器就绪 */
  private async ensureDecoder(): Promise<WebOpusDecoder> {
    if (!this.opusDecoder) {
      this.opusDecoder = new WebOpusDecoder({ sampleRate: 16000, channels: 1 })
      await this.opusDecoder.ready
    }
    return this.opusDecoder
  }

  /** V0.3：收一个 Opus 包，解码并累积到当前句。 */
  async enqueueOpus(opusBytes: ArrayBuffer): Promise<void> {
    const decoder = await this.ensureDecoder()
    try {
      const decoded = decoder.decodeFrame(new Uint8Array(opusBytes))
      if (decoded.channelData[0] && decoded.samplesDecoded > 0) {
        this.currentPcm.push(decoded.channelData[0])
        this.currentSampleRate = decoded.sampleRate
      }
    } catch (e) {
      console.warn('Opus 解码失败:', e)
    }
  }

  /** V0.3：标记当前句结束（收到 tts_stop），把累积的 PCM 拼成一句入队播放。 */
  flushSentence(): void {
    if (this.currentPcm.length === 0) return
    const total = this.currentPcm.reduce((s, arr) => s + arr.length, 0)
    const merged = new Float32Array(total)
    let offset = 0
    for (const arr of this.currentPcm) {
      merged.set(arr, offset)
      offset += arr.length
    }
    this.currentPcm = []
    this.queue.push({ pcm: merged, sampleRate: this.currentSampleRate })
    void this.playNext()
  }

  /** 兼容旧模式：入队一段完整 wav 字节并播放。 */
  async enqueueWav(wavBytes: ArrayBuffer): Promise<void> {
    this.ensureCtx()
    try {
      const buffer = await this.ctx!.decodeAudioData(wavBytes)
      const pcm = buffer.getChannelData(0)
      this.queue.push({ pcm: new Float32Array(pcm), sampleRate: buffer.sampleRate })
      void this.playNext()
    } catch (e) {
      console.warn('WAV 解码失败:', e)
    }
  }

  /** 便捷方法：从 URL（如 object URL）拉取 wav 并入队播放。失败静默不影响其他句。 */
  async enqueueWavUrl(url: string): Promise<void> {
    try {
      const res = await fetch(url)
      const wavBytes = await res.arrayBuffer()
      await this.enqueueWav(wavBytes)
    } catch (e) {
      console.warn('TTS URL 拉取失败:', e)
    }
  }

  /** 切换扬声器开关（gain 0/1）。 */
  setSpeakerOn(on: boolean): void {
    this.speakerOn = on
    if (this.gain) this.gain.gain.value = on ? 1 : 0
  }

  isSpeaking(): boolean {
    return this.playing
  }

  /** 立即停止当前播放并清空队列（打断/挂断用）。同时丢弃当前句累积的包。 */
  clear(): void {
    this.queue.splice(0)
    this.currentPcm = []
    if (this.source) {
      this.source.onended = null
      try { this.source.stop() } catch { /* 已停 */ }
      this.source = null
    }
    this.playing = false
  }

  /** 释放底层资源（组件卸载用）。 */
  dispose(): void {
    this.clear()
    if (this.opusDecoder) {
      this.opusDecoder.free()
      this.opusDecoder = null
    }
    this.gain = null
    if (this.ctx) {
      void this.ctx.close()
      this.ctx = null
    }
  }

  private async playNext(): Promise<void> {
    if (this.playing || this.queue.length === 0) return
    if (this.opts.isActive && !this.opts.isActive()) return
    this.playing = true
    try {
      this.ensureCtx()
      const item = this.queue.shift()
      if (!item) {
        this.playing = false
        return
      }
      if (this.opts.isActive && !this.opts.isActive()) {
        this.playing = false
        return
      }
      // Float32 PCM → AudioBuffer
      const buffer = this.ctx!.createBuffer(1, item.pcm.length, item.sampleRate)
      buffer.getChannelData(0).set(item.pcm)
      this.source = this.ctx!.createBufferSource()
      this.source.buffer = buffer
      this.source.connect(this.gain!)
      this.opts.onPlayStart?.()
      this.source.onended = () => {
        this.source = null
        this.playing = false
        this.opts.onPlayEnd?.()
        void this.playNext()
      }
      this.source.start()
    } catch (e) {
      console.warn('播放 TTS 失败:', e)
      this.playing = false
      void this.playNext()
    }
  }
}
