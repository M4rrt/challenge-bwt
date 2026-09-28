import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from './api'
import { issueChatToken, redeemExchangeCode } from './monolith'

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn())
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('redeemExchangeCode', () => {
  it('posts the code to the monolith and returns the renewal token plus service URLs', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          renewal_token: 'renewal-123',
          api_url: 'https://chat.example.com',
          ws_url: 'wss://chat.example.com',
        }),
        { status: 200 },
      ),
    )

    const result = await redeemExchangeCode('exchange-code-abc')

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:3000/chat/sessions/redeem',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ code: 'exchange-code-abc' }),
      }),
    )
    expect(result).toEqual({
      renewal_token: 'renewal-123',
      api_url: 'https://chat.example.com',
      ws_url: 'wss://chat.example.com',
    })
  })

  it('throws an ApiError with the response status on an invalid or already-used code', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: 'code already used' }), { status: 401 }),
    )

    await expect(redeemExchangeCode('stale-code')).rejects.toThrow(ApiError)
  })
})

describe('issueChatToken', () => {
  it('posts the renewal token to the monolith and returns a fresh chat token', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ access_token: 'chat-token-123', token_type: 'bearer' }), { status: 200 }),
    )

    const result = await issueChatToken('renewal-123')

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:3000/chat/sessions/token',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ renewal_token: 'renewal-123' }),
      }),
    )
    expect(result).toEqual({ access_token: 'chat-token-123', token_type: 'bearer' })
  })

  it('throws an ApiError with the response status when the renewal token is rejected', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: 'invalid renewal token' }), { status: 401 }),
    )

    await expect(issueChatToken('bad-token')).rejects.toThrow(ApiError)
  })
})
