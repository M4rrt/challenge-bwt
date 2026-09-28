import { isTokenExpired } from './jwt'

const DEFAULT_API_URL = 'http://localhost:8000'

export function toWsUrl(apiUrl: string): string {
  return apiUrl.replace(/^http/, 'ws')
}

function defaultApiUrl(): string {
  return (import.meta.env.VITE_API_URL as string | undefined) ?? DEFAULT_API_URL
}

let apiUrl = defaultApiUrl()
let wsUrl = toWsUrl(apiUrl)

export function getApiUrl(): string {
  return apiUrl
}

export function getWsUrl(): string {
  return wsUrl
}

/** Learned from the redemption response at runtime; the env var above is only the dev fallback until then. */
export function setServiceUrls(nextApiUrl: string, nextWsUrl: string): void {
  apiUrl = nextApiUrl
  wsUrl = nextWsUrl
}

/** Back to the dev-fallback host on logout, so a stale chat-service URL never survives into the next session. */
export function resetServiceUrls(): void {
  apiUrl = defaultApiUrl()
  wsUrl = toWsUrl(apiUrl)
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

/** Shared with monolith.ts, whose calls carry no auth/retry concerns but still need the same body-parsing. */
export function readJsonBody(response: Response): Promise<unknown> {
  return response.json().catch(() => undefined)
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

  const response = await fetch(`${getApiUrl()}${path}`, { ...options, headers })
  const body = await readJsonBody(response)

  if (!response.ok) {
    if (response.status === 401 && effectiveToken && refreshHandler && !isRetry) {
      const newToken = await refreshHandler()
      return apiFetch<T>(path, options, newToken, true)
    }
    throw new ApiError(response.status, body)
  }

  return body as T
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
