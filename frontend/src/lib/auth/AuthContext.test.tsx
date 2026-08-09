import type { ReactNode } from 'react'
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api'
import { AuthProvider, useAuth } from './AuthContext'

function wrapper({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>
}

beforeEach(() => {
  localStorage.clear()
})

afterEach(() => {
  vi.restoreAllMocks()
  api.setRefreshHandler(null)
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

  it('login stores the access and refresh tokens and flips isAuthenticated to true', () => {
    const { result } = renderHook(() => useAuth(), { wrapper })

    act(() => result.current.login('new-token', 'new-refresh-token'))

    expect(result.current.isAuthenticated).toBe(true)
    expect(localStorage.getItem('chat-app:token')).toBe('new-token')
    expect(localStorage.getItem('chat-app:refresh-token')).toBe('new-refresh-token')
  })

  it('logout clears both tokens and flips isAuthenticated to false', () => {
    localStorage.setItem('chat-app:token', 'existing-token')
    localStorage.setItem('chat-app:refresh-token', 'existing-refresh-token')
    vi.spyOn(api, 'logoutRequest').mockResolvedValue(undefined)
    const { result } = renderHook(() => useAuth(), { wrapper })

    act(() => result.current.logout())

    expect(result.current.isAuthenticated).toBe(false)
    expect(localStorage.getItem('chat-app:token')).toBeNull()
    expect(localStorage.getItem('chat-app:refresh-token')).toBeNull()
  })

  it('logout best-effort notifies the backend, but clears local state even if that call fails', async () => {
    localStorage.setItem('chat-app:token', 'existing-token')
    localStorage.setItem('chat-app:refresh-token', 'existing-refresh-token')
    const logoutRequestSpy = vi.spyOn(api, 'logoutRequest').mockRejectedValue(new Error('network error'))
    const { result } = renderHook(() => useAuth(), { wrapper })

    act(() => result.current.logout())

    expect(logoutRequestSpy).toHaveBeenCalledWith('existing-refresh-token')
    expect(result.current.isAuthenticated).toBe(false)
    expect(localStorage.getItem('chat-app:token')).toBeNull()
  })

  it('registers a refresh handler on api.ts while a refresh token is present', () => {
    const setRefreshHandlerSpy = vi.spyOn(api, 'setRefreshHandler')
    const { result } = renderHook(() => useAuth(), { wrapper })

    act(() => result.current.login('new-token', 'new-refresh-token'))

    expect(setRefreshHandlerSpy).toHaveBeenLastCalledWith(expect.any(Function))
  })

  it('the registered refresh handler exchanges the refresh token and persists the new access token', async () => {
    let capturedHandler: (() => Promise<string>) | null = null
    vi.spyOn(api, 'setRefreshHandler').mockImplementation((handler) => {
      capturedHandler = handler
    })
    vi.spyOn(api, 'refreshAccessToken').mockResolvedValue({
      access_token: 'refreshed-token',
      token_type: 'bearer',
    })
    const { result } = renderHook(() => useAuth(), { wrapper })
    act(() => result.current.login('old-token', 'stable-refresh-token'))

    const newToken = await act(() => capturedHandler!())

    expect(api.refreshAccessToken).toHaveBeenCalledWith('stable-refresh-token')
    expect(newToken).toBe('refreshed-token')
    expect(result.current.token).toBe('refreshed-token')
    expect(localStorage.getItem('chat-app:token')).toBe('refreshed-token')
  })

  it('the registered refresh handler forces a logout when the refresh call itself fails', async () => {
    let capturedHandler: (() => Promise<string>) | null = null
    vi.spyOn(api, 'setRefreshHandler').mockImplementation((handler) => {
      capturedHandler = handler
    })
    vi.spyOn(api, 'refreshAccessToken').mockRejectedValue(new api.ApiError(401, { detail: 'invalid' }))
    vi.spyOn(api, 'logoutRequest').mockResolvedValue(undefined)
    const { result } = renderHook(() => useAuth(), { wrapper })
    act(() => result.current.login('old-token', 'stale-refresh-token'))

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
