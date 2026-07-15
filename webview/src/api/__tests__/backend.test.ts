import { describe, it, expect, afterEach, vi } from 'vitest'
import {
  errorToZh,
  ApiRequestError,
  chat,
  type ErrorCode,
} from '../backend'

// errorToZh 是纯函数，直接测全码表
describe('errorToZh', () => {
  const codes: ErrorCode[] = [
    'INVALID_INPUT',
    'UPSTREAM_TIMEOUT',
    'TIMEOUT',
    'UPSTREAM_RATE_LIMITED',
    'UPSTREAM_UNAVAILABLE',
    'RESPONSE_INVALID',
    'CONTENT_BLOCKED',
    'NETWORK_ERROR',
    'INTERNAL_ERROR',
  ]

  it.each(codes)('为 %s 返回非空中文提示', (code) => {
    const msg = errorToZh({ code, message: 'x', retryable: false })
    expect(msg.length).toBeGreaterThan(0)
  })

  it('CONTENT_BLOCKED 提示为"换个说法"', () => {
    expect(errorToZh({ code: 'CONTENT_BLOCKED', message: '', retryable: false })).toContain('换个说法')
  })

  it('CONTENT_BLOCKED 与 UPSTREAM_UNAVAILABLE 提示不同（验证不再误判可重试）', () => {
    const blocked = errorToZh({ code: 'CONTENT_BLOCKED', message: '', retryable: false })
    const unavailable = errorToZh({ code: 'UPSTREAM_UNAVAILABLE', message: '', retryable: true })
    expect(blocked).not.toEqual(unavailable)
  })
})

// http() 对 422 错误信封的映射——mock global.fetch
describe('http 422 错误信封映射', () => {
  const originalFetch = global.fetch

  afterEach(() => {
    global.fetch = originalFetch
    vi.restoreAllMocks()
  })

  function mockFetch(status: number, body: unknown) {
    global.fetch = vi.fn().mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      statusText: '',
      json: async () => body,
      text: async () => JSON.stringify(body),
    } as unknown as Response)
  }

  it('422 + {code:CONTENT_BLOCKED, retryable:false} → ApiRequestError 不可重试', async () => {
    mockFetch(422, {
      ok: false,
      request_id: 'abc123',
      error: { code: 'CONTENT_BLOCKED', message: '内容被审核拦截', retryable: false },
    })
    await expect(chat('敏感词')).rejects.toMatchObject({
      code: 'CONTENT_BLOCKED',
      retryable: false,
      requestId: 'abc123',
    })
  })

  it('422 + 缺 code → 兜底 INTERNAL_ERROR + retryable:false', async () => {
    mockFetch(422, { ok: false, error: {} })
    await expect(chat('x')).rejects.toMatchObject({
      code: 'INTERNAL_ERROR',
      retryable: false,
    })
  })

  it('502 + {code:UPSTREAM_UNAVAILABLE, retryable:true} → 可重试', async () => {
    mockFetch(502, {
      ok: false,
      error: { code: 'UPSTREAM_UNAVAILABLE', message: '上游不可用', retryable: true },
    })
    await expect(chat('x')).rejects.toMatchObject({
      code: 'UPSTREAM_UNAVAILABLE',
      retryable: true,
    })
  })

  it('非错误信封的 500 → 兜底 UPSTREAM_UNAVAILABLE + 可重试', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: 'Internal',
      json: async () => { throw new Error('not json') },
      text: async () => 'plain text',
    } as unknown as Response)
    await expect(chat('x')).rejects.toMatchObject({
      code: 'UPSTREAM_UNAVAILABLE',
      retryable: true,
    })
  })
})

describe('ApiRequestError', () => {
  it('保留 code/retryable/requestId', () => {
    const e = new ApiRequestError({
      code: 'CONTENT_BLOCKED',
      message: 'blocked',
      retryable: false,
      requestId: 'r1',
    })
    expect(e.code).toBe('CONTENT_BLOCKED')
    expect(e.retryable).toBe(false)
    expect(e.requestId).toBe('r1')
    expect(e.message).toBe('blocked')
  })
})
