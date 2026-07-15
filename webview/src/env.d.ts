/// <reference types="vite/client" />

// opus-recorder 是 CommonJS 库，无自带 TS 类型
declare module 'opus-recorder' {
  interface RecorderOptions {
    encoderPath: string
    decoderPath?: string
    streamPages?: boolean
    originalSampleRateOverride?: number
    encoderSampleRate?: number
    encoderApplication?: number
    encoderFrameSize?: number
    numberOfChannels?: number
    bitRate?: number
    maxFramesPerPage?: number
    monitorGain?: number
    recorderGain?: number
  }

  interface RecorderInstance {
    start: () => Promise<void>
    stop: () => Promise<void>
    ondataavailability?: (arrayBuffer: ArrayBuffer) => void
    onstart?: () => void
    onstop?: () => void
    onError?: (err: unknown) => void
    stream: MediaStream | null
    close: () => void
  }

  const Recorder: { new (options: RecorderOptions): RecorderInstance }
  export default Recorder
}
