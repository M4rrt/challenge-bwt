import type { ReactNode } from 'react'
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api'
import { getApiUrl, getWsUrl, setServiceUrls } from '../api'
import * as monolith from '../monolith'
import { AuthProvider, useAuth } from './AuthContext'

const DEFAULT_API_URL = 'http://localhost:8000'
const DEFAULT_WS_URL = 'ws://localhost:8000'

function wrapper({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>
}

beforeEach(() => {
  localStorage.clear()
})

afterEach(() => {
  vi.restoreAllMocks()
  api.setRefreshHandler(null)
  setServiceUrls(DEFAULT_API_URL, DEFAULT_WS_URL)
})

describe('AuthContext', () => {
  it('is not authenticated when localStorage has no token', () => {
    const { result } = renderHook(() => useAuth(), { wrapper })

    expect(result.current.isAuthenticated).toBe(false)
  })

  it('is authenticated when localStorage already has a token on mount', () => {
    localStorage.setItem('chat-app:token', 'existing-token')

    const { result } = renderHook(() => useAuth(), { wrapper })

    expect(result.current.isAuthenticated).toBe(true)
    expect(result.current.token).toBe('existing-token')
  })

  it('restores the persisted service URLs on mount, before anything renders against them', () => {
    localStorage.setItem('chat-app:api-url', 'https://chat.example.com')
    localStorage.setItem('chat-app:ws-url', 'wss://chat.example.com')

    renderHook(() => useAuth(), { wrapper })

    expect(getApiUrl()).toBe('https://chat.example.com')
    expect(getWsUrl()).toBe('wss://chat.example.com')
  })

  it('login stores the chat token and renewal token, sets the service URLs, and flips isAuthenticated to true', () => {
    const { result } = renderHook(() => useAuth(), { wrapper })

    act(() =>
      result.current.login('new-token', 'new-renewal-token', 'https://chat.example.com', 'wss://chat.example.com'),
    )

    expect(result.current.isAuthenticated).toBe(true)
    expect(result.current.token).toBe('new-token')
    expect(localStorage.getItem('chat-app:token')).toBe('new-token')
    expect(localStorage.getItem('chat-app:renewal-token')).toBe('new-renewal-token')
    expect(localStorage.getItem('chat-app:api-url')).toBe('https://chat.example.com')
    expect(localStorage.getItem('chat-app:ws-url')).toBe('wss://chat.example.com')
    expect(getApiUrl()).toBe('https://chat.example.com')
    expect(getWsUrl()).toBe('wss://chat.example.com')
  })

  it('logout clears the chat token and renewal token and flips isAuthenticated to false', () => {
    localStorage.setItem('chat-app:token', 'existing-token')
    localStorage.setItem('chat-app:renewal-token', 'existing-renewal-token')
    const { result } = renderHook(() => useAuth(), { wrapper })

    act(() => result.current.logout())

    expect(result.current.isAuthenticated).toBe(false)
    expect(localStorage.getItem('chat-app:token')).toBeNull()
    expect(localStorage.getItem('chat-app:renewal-token')).toBeNull()
  })

  it('logout also resets the service URLs, so a stale chat-service host never survives into the next session', () => {
    const { result } = renderHook(() => useAuth(), { wrapper })
    act(() => result.current.login('token', 'renewal-token', 'https://chat.example.com', 'wss://chat.example.com'))

    act(() => result.current.logout())

    expect(localStorage.getItem('chat-app:api-url')).toBeNull()
    expect(localStorage.getItem('chat-app:ws-url')).toBeNull()
    expect(getApiUrl()).toBe(DEFAULT_API_URL)
    expect(getWsUrl()).toBe(DEFAULT_WS_URL)
  })

  it('registers a refresh handler on api.ts while a renewal token is present', () => {
    const setRefreshHandlerSpy = vi.spyOn(api, 'setRefreshHandler')
    const { result } = renderHook(() => useAuth(), { wrapper })

    act(() => result.current.login('new-token', 'new-renewal-token', DEFAULT_API_URL, DEFAULT_WS_URL))

    expect(setRefreshHandlerSpy).toHaveBeenLastCalledWith(expect.any(Function))
  })

  it('the registered refresh handler asks the monolith for a new chat token and persists it', async () => {
    let capturedHandler: (() => Promise<string>) | null = null
    vi.spyOn(api, 'setRefreshHandler').mockImplementation((handler) => {
      capturedHandler = handler
    })
    vi.spyOn(monolith, 'issueChatToken').mockResolvedValue({
      access_token: 'refreshed-token',
      token_type: 'bearer',
    })
    const { result } = renderHook(() => useAuth(), { wrapper })
    act(() => result.current.login('old-token', 'stable-renewal-token', DEFAULT_API_URL, DEFAULT_WS_URL))

    const newToken = await act(() => capturedHandler!())

    expect(monolith.issueChatToken).toHaveBeenCalledWith('stable-renewal-token')
    expect(newToken).toBe('refreshed-token')
    expect(result.current.token).toBe('refreshed-token')
    expect(localStorage.getItem('chat-app:token')).toBe('refreshed-token')
  })

  it('the registered refresh handler leaves the renewal token and service URLs untouched — only the chat token changes', async () => {
    let capturedHandler: (() => Promise<string>) | null = null
    vi.spyOn(api, 'setRefreshHandler').mockImplementation((handler) => {
      capturedHandler = handler
    })
    vi.spyOn(monolith, 'issueChatToken').mockResolvedValue({
      access_token: 'refreshed-token',
      token_type: 'bearer',
    })
    const { result } = renderHook(() => useAuth(), { wrapper })
    act(() =>
      result.current.login('old-token', 'stable-renewal-token', 'https://chat.example.com', 'wss://chat.example.com'),
    )

    await act(() => capturedHandler!())

    expect(localStorage.getItem('chat-app:renewal-token')).toBe('stable-renewal-token')
    expect(localStorage.getItem('chat-app:api-url')).toBe('https://chat.example.com')
    expect(getApiUrl()).toBe('https://chat.example.com')
    expect(getWsUrl()).toBe('wss://chat.example.com')
  })

  it('the registered refresh handler forces a logout when the monolith rejects the renewal token', async () => {
    let capturedHandler: (() => Promise<string>) | null = null
    vi.spyOn(api, 'setRefreshHandler').mockImplementation((handler) => {
      capturedHandler = handler
    })
    vi.spyOn(monolith, 'issueChatToken').mockRejectedValue(new api.ApiError(401, { detail: 'invalid' }))
    const { result } = renderHook(() => useAuth(), { wrapper })
    act(() => result.current.login('old-token', 'stale-renewal-token', DEFAULT_API_URL, DEFAULT_WS_URL))

    let caughtError: unknown
    await act(async () => {
      try {
        await capturedHandler!()
      } catch (error) {
        caughtError = error
      }
    })

    expect(caughtError).toBeInstanceOf(api.ApiError)
    expect(result.current.isAuthenticated).toBe(false)
    expect(localStorage.getItem('chat-app:token')).toBeNull()
  })
})
