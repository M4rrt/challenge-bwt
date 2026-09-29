import type { ReactNode } from 'react'
import { createContext, useContext, useEffect, useState } from 'react'
import { resetServiceUrls, setRefreshHandler, setServiceUrls } from '../api'
import { issueChatToken } from '../monolith'

const TOKEN_STORAGE_KEY = 'chat-app:token'
const RENEWAL_TOKEN_STORAGE_KEY = 'chat-app:renewal-token'
const API_URL_STORAGE_KEY = 'chat-app:api-url'
const WS_URL_STORAGE_KEY = 'chat-app:ws-url'

interface AuthContextValue {
  token: string | null
  renewalToken: string | null
  isAuthenticated: boolean
  login: (token: string, renewalToken: string, apiUrl: string, wsUrl: string) => void
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

/** Runs once, synchronously, before any child renders — a query gated on isAuthenticated must never fire against the dev-fallback URL. */
function restorePersistedServiceUrls() {
  const storedApiUrl = localStorage.getItem(API_URL_STORAGE_KEY)
  const storedWsUrl = localStorage.getItem(WS_URL_STORAGE_KEY)
  if (storedApiUrl && storedWsUrl) {
    setServiceUrls(storedApiUrl, storedWsUrl)
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => {
    restorePersistedServiceUrls()
    return localStorage.getItem(TOKEN_STORAGE_KEY)
  })
  const [renewalToken, setRenewalToken] = useState<string | null>(() =>
    localStorage.getItem(RENEWAL_TOKEN_STORAGE_KEY),
  )

  function login(newToken: string, newRenewalToken: string, apiUrl: string, wsUrl: string) {
    localStorage.setItem(TOKEN_STORAGE_KEY, newToken)
    localStorage.setItem(RENEWAL_TOKEN_STORAGE_KEY, newRenewalToken)
    localStorage.setItem(API_URL_STORAGE_KEY, apiUrl)
    localStorage.setItem(WS_URL_STORAGE_KEY, wsUrl)
    setServiceUrls(apiUrl, wsUrl)
    setToken(newToken)
    setRenewalToken(newRenewalToken)
  }

  function logout() {
    localStorage.removeItem(TOKEN_STORAGE_KEY)
    localStorage.removeItem(RENEWAL_TOKEN_STORAGE_KEY)
    localStorage.removeItem(API_URL_STORAGE_KEY)
    localStorage.removeItem(WS_URL_STORAGE_KEY)
    resetServiceUrls()
    setToken(null)
    setRenewalToken(null)
  }

  useEffect(() => {
    if (!renewalToken) {
      setRefreshHandler(null)
      return
    }

    setRefreshHandler(async () => {
      try {
        const result = await issueChatToken(renewalToken)
        localStorage.setItem(TOKEN_STORAGE_KEY, result.access_token)
        setToken(result.access_token)
        return result.access_token
      } catch (error) {
        logout()
        throw error
      }
    })

    return () => setRefreshHandler(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [renewalToken])

  return (
    <AuthContext.Provider value={{ token, renewalToken, isAuthenticated: token !== null, login, logout }}>
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
