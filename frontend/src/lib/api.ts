import { isTokenExpired } from './jwt'

const DEFAULT_API_URL = 'http://localhost:8000'

export const API_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? DEFAULT_API_URL

export function toWsUrl(apiUrl: string): string {
  return apiUrl.replace(/^http/, 'ws')
}

export class ApiError extends Error {
  readonly status: number
  readonly body: unknown

  constructor(status: number, body: unknown) {
    super(`API request failed with status ${status}`)
    this.status = status
    this.body = body
  }
}

type RefreshHandler = () => Promise<string>

let refreshHandler: RefreshHandler | null = null

export function setRefreshHandler(handler: RefreshHandler | null) {
  refreshHandler = handler
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
  isRetry = false,
): Promise<T> {
  let effectiveToken = token
  if (effectiveToken && refreshHandler && !isRetry && isTokenExpired(effectiveToken)) {
    effectiveToken = await refreshHandler()
  }

  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...(effectiveToken ? { Authorization: `Bearer ${effectiveToken}` } : {}),
    ...options.headers,
  }

  const response = await fetch(`${API_URL}${path}`, { ...options, headers })
  const body = await response.json().catch(() => undefined)

  if (!response.ok) {
    if (response.status === 401 && effectiveToken && refreshHandler && !isRetry) {
      const newToken = await refreshHandler()
      return apiFetch<T>(path, options, newToken, true)
    }
    throw new ApiError(response.status, body)
  }

  return body as T
}

export interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface AccessTokenResponse {
  access_token: string
  token_type: string
}

export interface RegisterResponse {
  id: string
  email: string
  username: string
}

export function login(email: string, password: string): Promise<LoginResponse> {
  return apiFetch<LoginResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}

export function refreshAccessToken(refreshToken: string): Promise<AccessTokenResponse> {
  return apiFetch<AccessTokenResponse>('/auth/refresh', {
    method: 'POST',
    body: JSON.stringify({ refresh_token: refreshToken }),
  })
}

export function logoutRequest(refreshToken: string): Promise<void> {
  return apiFetch<void>('/auth/logout', {
    method: 'POST',
    body: JSON.stringify({ refresh_token: refreshToken }),
  })
}

export function register(
  email: string,
  username: string,
  password: string,
): Promise<RegisterResponse> {
  return apiFetch<RegisterResponse>('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, username, password }),
  })
}

export interface CurrentUser {
  id: string
  email: string
  username: string
}

export interface UserSummary {
  id: string
  username: string
}

export interface Chat {
  id: string
  name: string | null
  participant_user_ids: string[]
  last_message_at: string | null
}

export function getMe(token: string): Promise<CurrentUser> {
  return apiFetch<CurrentUser>('/auth/me', {}, token)
}

export function listUsers(token: string): Promise<UserSummary[]> {
  return apiFetch<UserSummary[]>('/users', {}, token)
}

export function listChats(token: string): Promise<Chat[]> {
  return apiFetch<Chat[]>('/chats', {}, token)
}

export function createChat(
  participantUserIds: string[],
  name: string | undefined,
  token: string,
): Promise<Chat> {
  return apiFetch<Chat>(
    '/chats',
    {
      method: 'POST',
      body: JSON.stringify({ participant_user_ids: participantUserIds, name }),
    },
    token,
  )
}

export interface Message {
  id: string
  chat_id: string
  sender_id: string | null
  sender_type: string
  source_label: string | null
  body: string
  created_at: string
}

export function listMessages(chatId: string, token: string): Promise<Message[]> {
  return apiFetch<Message[]>(`/chats/${chatId}/messages`, {}, token)
}

export function sendMessage(
  chatId: string,
  body: string,
  token: string,
): Promise<Message> {
  return apiFetch<Message>(
    `/chats/${chatId}/messages`,
    { method: 'POST', body: JSON.stringify({ body }) },
    token,
  )
}

export function sendWebhookMessage(rawBody: string, signature: string): Promise<Message> {
  return apiFetch<Message>('/webhook/messages', {
    method: 'POST',
    body: rawBody,
    headers: { 'X-Signature': signature },
  })
}
