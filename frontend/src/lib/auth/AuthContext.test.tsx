import type { ReactNode } from 'react'
import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { AuthProvider, useAuth } from './AuthContext'

function wrapper({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>
}

beforeEach(() => {
  localStorage.clear()
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

  it('login stores the token and flips isAuthenticated to true', () => {
    const { result } = renderHook(() => useAuth(), { wrapper })

    act(() => result.current.login('new-token'))

    expect(result.current.isAuthenticated).toBe(true)
    expect(localStorage.getItem('chat-app:token')).toBe('new-token')
  })

  it('logout clears the token and flips isAuthenticated to false', () => {
    localStorage.setItem('chat-app:token', 'existing-token')
    const { result } = renderHook(() => useAuth(), { wrapper })

    act(() => result.current.logout())

    expect(result.current.isAuthenticated).toBe(false)
    expect(localStorage.getItem('chat-app:token')).toBeNull()
  })
})
