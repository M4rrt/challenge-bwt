import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from './api'
import { createChat, issueChatToken, listContacts, MONOLITH_URL, redeemExchangeCode } from './monolith'

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
      `${MONOLITH_URL}/chat/sessions/redeem`,
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
      `${MONOLITH_URL}/chat/sessions/token`,
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

describe('listContacts', () => {
  it('gets the contact/staff listing from the monolith, authenticated with the renewal token', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify([{ id: 'user-1', display_name: 'Beto', avatar_url: null, kind: 'staff' }]),
        { status: 200 },
      ),
    )

    const result = await listContacts('renewal-123')

    expect(fetch).toHaveBeenCalledWith(
      `${MONOLITH_URL}/chat/contacts`,
      expect.objectContaining({
        method: 'GET',
        headers: expect.objectContaining({ Authorization: 'Bearer renewal-123' }),
      }),
    )
    expect(result).toEqual([{ id: 'user-1', display_name: 'Beto', avatar_url: null, kind: 'staff' }])
  })

  it('sends a search param when given', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }))

    await listContacts('renewal-123', 'bet')

    expect(fetch).toHaveBeenCalledWith(
      `${MONOLITH_URL}/chat/contacts?search=bet`,
      expect.anything(),
    )
  })

  it('throws an ApiError with the response status on a rejected renewal token', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ detail: 'expired' }), { status: 401 }))

    await expect(listContacts('bad-token')).rejects.toThrow(ApiError)
  })
})

describe('createChat', () => {
  it('posts the participant ids and name to the monolith, authenticated with the renewal token', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ chat_id: 'chat-1' }), { status: 200 }),
    )

    const result = await createChat('renewal-123', ['user-1', 'user-2'], 'Trio')

    expect(fetch).toHaveBeenCalledWith(
      `${MONOLITH_URL}/chat/chats`,
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ participant_ids: ['user-1', 'user-2'], name: 'Trio' }),
        headers: expect.objectContaining({ Authorization: 'Bearer renewal-123' }),
      }),
    )
    expect(result).toEqual({ chat_id: 'chat-1' })
  })

  it('omits name from the body when not given, for a 1:1', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ chat_id: 'chat-2' }), { status: 200 }),
    )

    await createChat('renewal-123', ['user-1'])

    expect(fetch).toHaveBeenCalledWith(
      `${MONOLITH_URL}/chat/chats`,
      expect.objectContaining({ body: JSON.stringify({ participant_ids: ['user-1'] }) }),
    )
  })

  it('throws an ApiError with the response status on a monolith-side rejection', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: 'not an active contact' }), { status: 422 }),
    )

    await expect(createChat('renewal-123', ['user-1'])).rejects.toThrow(ApiError)
  })
})
