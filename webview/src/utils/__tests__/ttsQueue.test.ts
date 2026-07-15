import { describe, it, expect, vi, beforeEach } from 'vitest'
import { TtsQueue } from '../ttsQueue'

// mock AudioContext：记录 start/stop 顺序，onended 由测试手动触发以模拟播放完成
function makeMockCtx() {
  const started: number[] = []
  const stopped: number[] = []
  let nextId = 1
  const sources: { id: number; onended: (() => void) | null; stopped: boolean }[] = []

  const gain = { gain: { value: 1 }, connect: vi.fn() }
  const ctx: any = {
    destination: {},
    createGain: vi.fn(() => gain),
    decodeAudioData: vi.fn(async () => ({
      getChannelData: () => new Float32Array(8),
      sampleRate: 16000,
    })),
    createBuffer: vi.fn((_channels: number, length: number) => ({
      getChannelData: () => new Float32Array(length),
    })),
    createBufferSource: vi.fn(() => {
      const id = nextId++
      const src = {
        id,
        buffer: null,
        onended: null as (() => void) | null,
        connect: vi.fn(),
        start: vi.fn(() => { started.push(id) }),
        stop: vi.fn(() => {
          if (!sources.find((s) => s.id === id)?.stopped) {
            stopped.push(id)
            sources.find((s) => s.id === id)!.stopped = true
          }
        }),
      }
      sources.push({ id, onended: src.onended, stopped: false })
      return src
    }),
    close: vi.fn(async () => {}),
  }
  return { ctx, gain, started, stopped, sources }
}

describe('TtsQueue 串行播放', () => {
  let mock: ReturnType<typeof makeMockCtx>

  beforeEach(() => {
    mock = makeMockCtx()
    vi.stubGlobal('AudioContext', vi.fn(() => mock.ctx))
  })

  it('3 段严格按入队顺序播放，无重叠', async () => {
    const q = new TtsQueue({ isActive: () => true })
    await q.enqueueWav(new ArrayBuffer(8))
    await q.enqueueWav(new ArrayBuffer(8))
    await q.enqueueWav(new ArrayBuffer(8))

    // 第一段应已 start
    await vi.waitFor(() => expect(mock.started).toEqual([1]))

    // 第一段未结束前，第二段不应 start（无重叠）
    expect(mock.started).toEqual([1])

    // 触发第一段结束
    const src1 = mock.ctx.createBufferSource.mock.results[0].value
    src1.onended?.()
    await vi.waitFor(() => expect(mock.started).toEqual([1, 2]))

    const src2 = mock.ctx.createBufferSource.mock.results[1].value
    src2.onended?.()
    await vi.waitFor(() => expect(mock.started).toEqual([1, 2, 3]))

    const src3 = mock.ctx.createBufferSource.mock.results[2].value
    src3.onended?.()
    // 队列空，不再有第 4 段
    await new Promise((r) => setTimeout(r, 0))
    expect(mock.started).toEqual([1, 2, 3])
  })

  it('clear() 立即停掉当前段且不再播后续', async () => {
    const q = new TtsQueue({ isActive: () => true })
    await q.enqueueWav(new ArrayBuffer(8))
    await q.enqueueWav(new ArrayBuffer(8))
    await vi.waitFor(() => expect(mock.started).toEqual([1]))

    q.clear()
    // 当前 source 被停
    expect(mock.stopped).toContain(1)
    // 第二段不应被 start
    await new Promise((r) => setTimeout(r, 10))
    expect(mock.started).toEqual([1])
    expect(q.isSpeaking()).toBe(false)
  })

  it('isActive=false 时不消费队列', async () => {
    let active = false
    const q = new TtsQueue({ isActive: () => active })
    await q.enqueueWav(new ArrayBuffer(8))
    await new Promise((r) => setTimeout(r, 10))
    expect(mock.started).toEqual([])

    // 激活后通过 enqueue 触发消费
    active = true
    await q.enqueueWav(new ArrayBuffer(8))
    await vi.waitFor(() => expect(mock.started.length).toBeGreaterThan(0))
  })

  it('setSpeakerOn(false) 把 gain 设为 0', async () => {
    const q = new TtsQueue({ isActive: () => true })
    await q.enqueueWav(new ArrayBuffer(8))
    await vi.waitFor(() => expect(mock.started).toEqual([1]))
    q.setSpeakerOn(false)
    expect(mock.gain.gain.value).toBe(0)
    q.setSpeakerOn(true)
    expect(mock.gain.gain.value).toBe(1)
  })

  it('onPlayStart/onPlayEnd 回调驱动状态', async () => {
    const starts: number[] = []
    const ends: number[] = []
    const q = new TtsQueue({
      isActive: () => true,
      onPlayStart: () => starts.push(1),
      onPlayEnd: () => ends.push(1),
    })
    await q.enqueueWav(new ArrayBuffer(8))
    await vi.waitFor(() => expect(starts).toEqual([1]))
    const src = mock.ctx.createBufferSource.mock.results[0].value
    src.onended?.()
    await vi.waitFor(() => expect(ends).toEqual([1]))
  })
})
