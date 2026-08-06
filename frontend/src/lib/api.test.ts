import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  ApiError,
  apiFetch,
  createConversation,
  getMe,
  listConversations,
  listUsers,
  login,
  register,
} from './api'

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn())
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('login', () => {
  it('posts credentials to /auth/login and returns the parsed token', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ access_token: 'token-123', token_type: 'bearer' }), {
        status: 200,
      }),
    )

    const result = await login('ana@example.com', 'Senha-Forte-123')

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/auth/login',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ email: 'ana@example.com', password: 'Senha-Forte-123' }),
      }),
    )
    expect(result).toEqual({ access_token: 'token-123', token_type: 'bearer' })
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
})
