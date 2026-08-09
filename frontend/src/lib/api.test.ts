import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  ApiError,
  apiFetch,
  createConversation,
  getMe,
  listConversations,
  listMessages,
  listUsers,
  login,
  logoutRequest,
  refreshAccessToken,
  register,
  sendMessage,
  sendWebhookMessage,
  setRefreshHandler,
  toWsUrl,
} from './api'

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
})

describe('login', () => {
  it('posts credentials to /auth/login and returns the parsed token', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify({ access_token: 'token-123', refresh_token: 'refresh-123', token_type: 'bearer' }),
        { status: 200 },
      ),
    )

    const result = await login('ana@example.com', 'Senha-Forte-123')

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/auth/login',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ email: 'ana@example.com', password: 'Senha-Forte-123' }),
      }),
    )
    expect(result).toEqual({ access_token: 'token-123', refresh_token: 'refresh-123', token_type: 'bearer' })
  })

  it('throws an ApiError with the response status on failure', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: 'invalid credentials' }), { status: 401 }),
    )

    await expect(login('ana@example.com', 'wrong-password')).rejects.toThrow(ApiError)
  })
})

describe('register', () => {
  it('posts credentials to /auth/register and returns the created user', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify({ id: 'user-1', email: 'ana@example.com', username: 'ana' }),
        { status: 201 },
      ),
    )

    const result = await register('ana@example.com', 'ana', 'Senha-Forte-123')

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/auth/register',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ email: 'ana@example.com', username: 'ana', password: 'Senha-Forte-123' }),
      }),
    )
    expect(result).toEqual({ id: 'user-1', email: 'ana@example.com', username: 'ana' })
  })
})

describe('getMe', () => {
  it('fetches the current user with the given token', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify({ id: 'user-1', email: 'ana@example.com', username: 'ana' }),
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
    expect(result).toEqual({ id: 'user-1', email: 'ana@example.com', username: 'ana' })
  })
})

describe('listUsers', () => {
  it('fetches all users with the given token', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify([{ id: 'user-1', username: 'ana' }]), { status: 200 }),
    )

    const result = await listUsers('token-123')

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/users',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer token-123' }),
      }),
    )
    expect(result).toEqual([{ id: 'user-1', username: 'ana' }])
  })
})

describe('listConversations', () => {
  it('fetches the caller conversations with the given token', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify([{ id: 'conv-1', name: null, participant_user_ids: ['user-1', 'user-2'] }]),
        { status: 200 },
      ),
    )

    const result = await listConversations('token-123')

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/conversations',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer token-123' }),
      }),
    )
    expect(result).toEqual([{ id: 'conv-1', name: null, participant_user_ids: ['user-1', 'user-2'] }])
  })
})

describe('createConversation', () => {
  it('posts participant ids and an optional name with the given token', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify({ id: 'conv-1', name: 'Trio', participant_user_ids: ['user-1', 'user-2', 'user-3'] }),
        { status: 201 },
      ),
    )

    const result = await createConversation(['user-2', 'user-3'], 'Trio', 'token-123')

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/conversations',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ participant_user_ids: ['user-2', 'user-3'], name: 'Trio' }),
        headers: expect.objectContaining({ Authorization: 'Bearer token-123' }),
      }),
    )
    expect(result).toEqual({
      id: 'conv-1',
      name: 'Trio',
      participant_user_ids: ['user-1', 'user-2', 'user-3'],
    })
  })
})

describe('listMessages', () => {
  it('fetches a conversation message backlog with the given token', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify([
          {
            id: 'msg-1',
            conversation_id: 'conv-1',
            sender_id: 'user-1',
            sender_type: 'user',
            source_label: null,
            body: 'oi',
            created_at: '2026-08-06T12:00:00Z',
          },
        ]),
        { status: 200 },
      ),
    )

    const result = await listMessages('conv-1', 'token-123')

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/conversations/conv-1/messages',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer token-123' }),
      }),
    )
    expect(result).toEqual([
      {
        id: 'msg-1',
        conversation_id: 'conv-1',
        sender_id: 'user-1',
        sender_type: 'user',
        source_label: null,
        body: 'oi',
        created_at: '2026-08-06T12:00:00Z',
      },
    ])
  })
})

describe('sendMessage', () => {
  it('posts a message body to a conversation with the given token', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          id: 'msg-1',
          conversation_id: 'conv-1',
          sender_id: 'user-1',
          sender_type: 'user',
          source_label: null,
          body: 'oi',
          created_at: '2026-08-06T12:00:00Z',
        }),
        { status: 201 },
      ),
    )

    const result = await sendMessage('conv-1', 'oi', 'token-123')

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/conversations/conv-1/messages',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ body: 'oi' }),
        headers: expect.objectContaining({ Authorization: 'Bearer token-123' }),
      }),
    )
    expect(result).toEqual({
      id: 'msg-1',
      conversation_id: 'conv-1',
      sender_id: 'user-1',
      sender_type: 'user',
      source_label: null,
      body: 'oi',
      created_at: '2026-08-06T12:00:00Z',
    })
  })
})

describe('sendWebhookMessage', () => {
  it('posts the exact raw body string with the given signature and no Authorization header', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          id: 'msg-1',
          conversation_id: 'conv-1',
          sender_id: null,
          sender_type: 'external',
          source_label: 'crm',
          body: 'oi',
          created_at: '2026-08-06T12:00:00Z',
        }),
        { status: 201 },
      ),
    )
    const rawBody = JSON.stringify({ conversation_id: 'conv-1', body: 'oi', source_label: 'crm' })

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
      conversation_id: 'conv-1',
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

describe('refreshAccessToken', () => {
  it('posts the refresh token to /auth/refresh and returns the new access token', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ access_token: 'new-token', token_type: 'bearer' }), { status: 200 }),
    )

    const result = await refreshAccessToken('refresh-123')

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/auth/refresh',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ refresh_token: 'refresh-123' }),
      }),
    )
    expect(result).toEqual({ access_token: 'new-token', token_type: 'bearer' })
  })

  it('throws an ApiError with the response status on failure', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: 'invalid refresh token' }), { status: 401 }),
    )

    await expect(refreshAccessToken('bad-token')).rejects.toThrow(ApiError)
  })
})

describe('logoutRequest', () => {
  it('posts the refresh token to /auth/logout', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 204 }))

    await logoutRequest('refresh-123')

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/auth/logout',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ refresh_token: 'refresh-123' }),
      }),
    )
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
