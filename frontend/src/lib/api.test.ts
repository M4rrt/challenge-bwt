import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, login, register } from './api'

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
      new Response(JSON.stringify({ id: 'user-1', email: 'ana@example.com' }), { status: 201 }),
    )

    const result = await register('ana@example.com', 'Senha-Forte-123')

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/auth/register',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ email: 'ana@example.com', password: 'Senha-Forte-123' }),
      }),
    )
    expect(result).toEqual({ id: 'user-1', email: 'ana@example.com' })
  })
})
