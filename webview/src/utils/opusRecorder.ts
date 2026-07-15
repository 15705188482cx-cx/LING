/**
 * Opus 录音封装 —— 用 opus-recorder 直接录 Opus 包发 WebSocket。
 *
 * V0.3：替代旧的 MediaRecorder webm→WAV 方案。
 * - 录音直接出 Opus（16kHz/mono/60ms 帧），与后端 opus_codec 对齐
 * - 每个 Opus 包通过 onOpusPacket 回调发出（走 WS 二进制帧）
 * - 不再有定长 4 秒切段，持续录音 + 服务端 VAD 自动断句
 *
 * 类型声明见 src/env.d.ts（库无自带 .d.ts）
 */

import Recorder from 'opus-recorder'

// encoderFrameSize=60ms 与后端一致；encoderApplication=2048(VOICE) 适合语音
// 类型见 src/env.d.ts
const RECORDER_OPTS = {
  encoderPath: '/opus-recorder/encoderWorker.min.js',
  decoderPath: '/opus-recorder/decoderWorker.min.js',
  streamPages: true,
  encoderSampleRate: 16000,
  encoderApplication: 2048, // VOIP
  encoderFrameSize: 60, // 60ms，与后端 OPUS_FRAME_MS 对齐
  numberOfChannels: 1,
  bitRate: 24000,
}

export interface OpusRecorderCallbacks {
  onOpusPacket: (packet: ArrayBuffer) => void
  onStart?: () => void
  onStop?: () => void
  onError?: (err: unknown) => void
}

export class OpusRecorder {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private recorder: any = null
  private cbs: OpusRecorderCallbacks

  constructor(cbs: OpusRecorderCallbacks) {
    this.cbs = cbs
  }

  /** 用已有 MediaStream（复用 VideoCall 的 getUserMedia 流）开始录音 */
  async startFromStream(stream: MediaStream): Promise<void> {
    if (this.recorder) return
    const recorder = new Recorder(RECORDER_OPTS)
    recorder.ondataavailability = (buf: ArrayBuffer) => {
      // streamPages=true 时，每个 Opus 包回调一次
      this.cbs.onOpusPacket(buf)
    }
    recorder.onstart = () => this.cbs.onStart?.()
    recorder.onstop = () => this.cbs.onStop?.()
    recorder.onError = (err: unknown) => this.cbs.onError?.(err)
    // opus-recorder 用 stream 属性接收外部流
    recorder.stream = stream
    this.recorder = recorder
    await recorder.start()
  }

  /** 停止录音 */
  async stop(): Promise<void> {
    if (this.recorder) {
      await this.recorder.stop()
      this.recorder.close()
      this.recorder = null
    }
  }

  /** 是否正在录音 */
  get isRecording(): boolean {
    return this.recorder !== null
  }
}
