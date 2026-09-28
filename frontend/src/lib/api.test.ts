import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  ApiError,
  apiFetch,
  getApiUrl,
  getMe,
  getWsUrl,
  listChats,
  listMessages,
  markRead,
  refreshToken,
  resetServiceUrls,
  sendMessage,
  sendWebhookMessage,
  setRefreshHandler,
  setServiceUrls,
  toWsUrl,
} from './api'

const DEFAULT_API_URL = 'http://localhost:8000'
const DEFAULT_WS_URL = 'ws://localhost:8000'

function makeJwt(payload: Record<string, unknown>): string {
  const encode = (value: unknown) =>
    btoa(JSON.stringify(value)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  return `${encode({ alg: 'HS256', typ: 'JWT' })}.${encode(payload)}.fake-signature`
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn())
})

afterEach(() => {
  vi.unstubAllGlobals()
  setRefreshHandler(null)
  setServiceUrls(DEFAULT_API_URL, DEFAULT_WS_URL)
})

describe('getMe', () => {
  it('fetches the current caller with the given token', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          id: 'user-1',
          company_id: 'company-1',
          user_kind: 'staff',
          scopes: [],
          display_name: 'Ana',
          avatar_url: null,
        }),
        { status: 200 },
      ),
    )

    const result = await getMe('token-123')

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/auth/me',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer token-123' }),
      }),
    )
    expect(result).toEqual({
      id: 'user-1',
      company_id: 'company-1',
      user_kind: 'staff',
      scopes: [],
      display_name: 'Ana',
      avatar_url: null,
    })
  })
})

describe('listChats', () => {
  it('fetches a page of the caller chats with the given token', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          chats: [{ id: 'chat-1', name: null, participant_user_ids: ['user-1', 'user-2'] }],
          next_cursor: null,
        }),
        { status: 200 },
      ),
    )

    const result = await listChats('token-123')

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/chats',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer token-123' }),
      }),
    )
    expect(result).toEqual({
      chats: [{ id: 'chat-1', name: null, participant_user_ids: ['user-1', 'user-2'] }],
      next_cursor: null,
    })
  })

  it('sends search and before as query params when given', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ chats: [], next_cursor: null }), { status: 200 }),
    )

    await listChats('token-123', { search: 'bet o', before: 'cursor-1' })

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/chats?search=bet+o&before=cursor-1',
      expect.anything(),
    )
  })

  it('omits query params that were not given', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ chats: [], next_cursor: null }), { status: 200 }),
    )

    await listChats('token-123')

    expect(fetch).toHaveBeenCalledWith('http://localhost:8000/chats', expect.anything())
  })
})

describe('listMessages', () => {
  it('fetches a page of a chat message backlog with the given token', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          messages: [
            {
              id: 'msg-1',
              chat_id: 'chat-1',
              sender_id: 'user-1',
              sender_type: 'user',
              source_label: null,
              body: 'oi',
              created_at: '2026-08-06T12:00:00Z',
            },
          ],
          next_cursor: null,
        }),
        { status: 200 },
      ),
    )

    const result = await listMessages('chat-1', 'token-123')

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/chats/chat-1/messages',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer token-123' }),
      }),
    )
    expect(result).toEqual({
      messages: [
        {
          id: 'msg-1',
          chat_id: 'chat-1',
          sender_id: 'user-1',
          sender_type: 'user',
          source_label: null,
          body: 'oi',
          created_at: '2026-08-06T12:00:00Z',
        },
      ],
      next_cursor: null,
    })
  })

  it('sends before as a query param when given', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ messages: [], next_cursor: null }), { status: 200 }),
    )

    await listMessages('chat-1', 'token-123', { before: 'cursor-1' })

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/chats/chat-1/messages?before=cursor-1',
      expect.anything(),
    )
  })
})

describe('sendMessage', () => {
  it('posts a message body and client message id to a chat with the given token, defaulting visibility to all', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          id: 'msg-1',
          chat_id: 'chat-1',
          sender_id: 'user-1',
          sender_type: 'user',
          source_label: null,
          body: 'oi',
          created_at: '2026-08-06T12:00:00Z',
        }),
        { status: 201 },
      ),
    )

    const result = await sendMessage('chat-1', 'oi', 'client-msg-1', 'token-123')

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/chats/chat-1/messages',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ body: 'oi', client_message_id: 'client-msg-1', visibility: 'all' }),
        headers: expect.objectContaining({ Authorization: 'Bearer token-123' }),
      }),
    )
    expect(result).toEqual({
      id: 'msg-1',
      chat_id: 'chat-1',
      sender_id: 'user-1',
      sender_type: 'user',
      source_label: null,
      body: 'oi',
      created_at: '2026-08-06T12:00:00Z',
    })
  })

  it('posts the given visibility when one is passed', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ id: 'msg-1' }), { status: 201 }),
    )

    await sendMessage('chat-1', 'nota interna', 'client-msg-2', 'token-123', 'staff_only')

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/chats/chat-1/messages',
      expect.objectContaining({
        body: JSON.stringify({
          body: 'nota interna',
          client_message_id: 'client-msg-2',
          visibility: 'staff_only',
        }),
      }),
    )
  })
})

describe('markRead', () => {
  it('posts the read watermark to a chat with the given token', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify({ last_read_at: '2026-08-06T12:00:00Z', last_read_message_id: 'msg-1' }),
        { status: 200 },
      ),
    )

    const result = await markRead(
      'chat-1',
      { read_at: '2026-08-06T12:00:00Z', message_id: 'msg-1' },
      'token-123',
    )

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/chats/chat-1/read',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ read_at: '2026-08-06T12:00:00Z', message_id: 'msg-1' }),
        headers: expect.objectContaining({ Authorization: 'Bearer token-123' }),
      }),
    )
    expect(result).toEqual({ last_read_at: '2026-08-06T12:00:00Z', last_read_message_id: 'msg-1' })
  })
})

describe('refreshToken', () => {
  it('rejects when no refresh handler has been registered', async () => {
    await expect(refreshToken()).rejects.toThrow()
  })

  it('delegates to the registered refresh handler', async () => {
    const handler = vi.fn().mockResolvedValue('new-token')
    setRefreshHandler(handler)

    await expect(refreshToken()).resolves.toBe('new-token')
    expect(handler).toHaveBeenCalledTimes(1)
  })
})

describe('sendWebhookMessage', () => {
  it('posts the exact raw body string with the given signature and no Authorization header', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          id: 'msg-1',
          chat_id: 'chat-1',
          sender_id: null,
          sender_type: 'external',
          source_label: 'crm',
          body: 'oi',
          created_at: '2026-08-06T12:00:00Z',
        }),
        { status: 201 },
      ),
    )
    const rawBody = JSON.stringify({ chat_id: 'chat-1', body: 'oi', source_label: 'crm' })

    const result = await sendWebhookMessage(rawBody, 'deadbeef')

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/webhook/messages',
      expect.objectContaining({
        method: 'POST',
        body: rawBody,
        headers: expect.objectContaining({ 'X-Signature': 'deadbeef' }),
      }),
    )
    const [, options] = vi.mocked(fetch).mock.calls[0]
    expect((options?.headers as Record<string, string> | undefined)?.Authorization).toBeUndefined()
    expect(result).toEqual({
      id: 'msg-1',
      chat_id: 'chat-1',
      sender_id: null,
      sender_type: 'external',
      source_label: 'crm',
      body: 'oi',
      created_at: '2026-08-06T12:00:00Z',
    })
  })

  it('throws an ApiError with the response status on failure', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: 'invalid signature' }), { status: 401 }),
    )

    await expect(sendWebhookMessage('{}', 'bad-signature')).rejects.toThrow(ApiError)
  })
})

describe('toWsUrl', () => {
  it('swaps http for ws', () => {
    expect(toWsUrl('http://localhost:8000')).toBe('ws://localhost:8000')
  })

  it('swaps https for wss', () => {
    expect(toWsUrl('https://api.example.com')).toBe('wss://api.example.com')
  })
})

describe('getApiUrl / getWsUrl / setServiceUrls', () => {
  it('default to the build-time env var when redemption has not run yet', () => {
    expect(getApiUrl()).toBe(DEFAULT_API_URL)
    expect(getWsUrl()).toBe(DEFAULT_WS_URL)
  })

  it('setServiceUrls overrides both at runtime', () => {
    setServiceUrls('https://chat.example.com', 'wss://chat.example.com')

    expect(getApiUrl()).toBe('https://chat.example.com')
    expect(getWsUrl()).toBe('wss://chat.example.com')
  })

  it('apiFetch targets whatever setServiceUrls last set', async () => {
    setServiceUrls('https://chat.example.com', 'wss://chat.example.com')
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }))

    await apiFetch('/some/path')

    expect(fetch).toHaveBeenCalledWith('https://chat.example.com/some/path', expect.anything())
  })

  it('resetServiceUrls reverts to the build-time env fallback', () => {
    setServiceUrls('https://chat.example.com', 'wss://chat.example.com')

    resetServiceUrls()

    expect(getApiUrl()).toBe(DEFAULT_API_URL)
    expect(getWsUrl()).toBe(DEFAULT_WS_URL)
  })
})

describe('apiFetch', () => {
  it('attaches an Authorization header when a token is passed', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }))

    await apiFetch('/some/path', {}, 'token-123')

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/some/path',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer token-123' }),
      }),
    )
  })

  it('on a 401 with a registered refresh handler, silently refreshes and retries once with the new token', async () => {
    const notYetExpiredToken = makeJwt({ exp: Math.floor(Date.now() / 1000) + 3600 })
    vi.mocked(fetch)
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'expired' }), { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200 }))
    const handler = vi.fn().mockResolvedValue('new-token')
    setRefreshHandler(handler)

    const result = await apiFetch('/some/path', {}, notYetExpiredToken)

    expect(handler).toHaveBeenCalledTimes(1)
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(fetch).toHaveBeenNthCalledWith(
      2,
      'http://localhost:8000/some/path',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer new-token' }),
      }),
    )
    expect(result).toEqual({ ok: true })
  })

  it('propagates the error without retrying when the refresh handler itself fails', async () => {
    const notYetExpiredToken = makeJwt({ exp: Math.floor(Date.now() / 1000) + 3600 })
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'expired' }), { status: 401 }),
    )
    const handler = vi.fn().mockRejectedValue(new ApiError(401, { detail: 'invalid refresh token' }))
    setRefreshHandler(handler)

    await expect(apiFetch('/some/path', {}, notYetExpiredToken)).rejects.toThrow(ApiError)
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('does not attempt a refresh when no token was used for the call', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ detail: 'unauthorized' }), { status: 401 }))
    const handler = vi.fn()
    setRefreshHandler(handler)

    await expect(apiFetch('/some/path')).rejects.toThrow(ApiError)
    expect(handler).not.toHaveBeenCalled()
  })

  it('proactively refreshes an already-expired token before making the call, avoiding a wasted 401 round trip', async () => {
    const expiredToken = makeJwt({ exp: Math.floor(Date.now() / 1000) - 60 })
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }))
    const handler = vi.fn().mockResolvedValue('new-token')
    setRefreshHandler(handler)

    const result = await apiFetch('/some/path', {}, expiredToken)

    expect(handler).toHaveBeenCalledTimes(1)
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/some/path',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer new-token' }),
      }),
    )
    expect(result).toEqual({ ok: true })
  })

  it('does not proactively refresh a token that is not expired', async () => {
    const validToken = makeJwt({ exp: Math.floor(Date.now() / 1000) + 3600 })
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }))
    const handler = vi.fn()
    setRefreshHandler(handler)

    await apiFetch('/some/path', {}, validToken)

    expect(handler).not.toHaveBeenCalled()
    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/some/path',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: `Bearer ${validToken}` }),
      }),
    )
  })
})
