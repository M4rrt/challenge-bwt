import type { ReactNode } from 'react'
import { createContext, useContext, useEffect, useState } from 'react'
import { logoutRequest, refreshAccessToken, setRefreshHandler } from '../api'

const TOKEN_STORAGE_KEY = 'chat-app:token'
const REFRESH_TOKEN_STORAGE_KEY = 'chat-app:refresh-token'

interface AuthContextValue {
  token: string | null
  isAuthenticated: boolean
  login: (token: string, refreshToken: string) => void
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() =>
    localStorage.getItem(TOKEN_STORAGE_KEY),
  )
  const [refreshToken, setRefreshTokenState] = useState<string | null>(() =>
    localStorage.getItem(REFRESH_TOKEN_STORAGE_KEY),
  )

  function login(newToken: string, newRefreshToken: string) {
    localStorage.setItem(TOKEN_STORAGE_KEY, newToken)
    localStorage.setItem(REFRESH_TOKEN_STORAGE_KEY, newRefreshToken)
    setToken(newToken)
    setRefreshTokenState(newRefreshToken)
  }

  function logout() {
    if (refreshToken) {
      logoutRequest(refreshToken).catch(() => {})
    }
    localStorage.removeItem(TOKEN_STORAGE_KEY)
    localStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY)
    setToken(null)
    setRefreshTokenState(null)
  }

  useEffect(() => {
    if (!refreshToken) {
      setRefreshHandler(null)
      return
    }

    setRefreshHandler(async () => {
      try {
        const result = await refreshAccessToken(refreshToken)
        login(result.access_token, refreshToken)
        return result.access_token
      } catch (error) {
        logout()
        throw error
      }
    })

    return () => setRefreshHandler(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshToken])

  return (
    <AuthContext.Provider value={{ token, isAuthenticated: token !== null, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
