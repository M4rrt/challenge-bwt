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

/** The same credential refresh apiFetch uses on a 401 or a proactive expiry check, exposed for the WebSocket hooks. */
export function refreshToken(): Promise<string> {
  if (!refreshHandler) {
    return Promise.reject(new Error('no refresh handler registered'))
  }
  return refreshHandler()
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

/** The wire shape of `app.schemas.caller.CallerRead` — everything this service knows about the caller from their token, and nothing more (it holds no user table). */
export interface CurrentUser {
  id: string
  company_id: string
  user_kind: 'staff' | 'client'
  scopes: string[]
  display_name: string | null
  avatar_url: string | null
}

export type ChatType = 'staff' | 'client'
export type MessageVisibility = 'all' | 'staff_only'

export interface Chat {
  id: string
  type: ChatType
  name: string | null
  participant_user_ids: string[]
  last_message: Message | null
  last_message_at: string | null
  unread_count: number
  last_read_at: string | null
  last_read_message_id: string | null
}

export interface ChatPage {
  chats: Chat[]
  next_cursor: string | null
}

export function getMe(token: string): Promise<CurrentUser> {
  return apiFetch<CurrentUser>('/auth/me', {}, token)
}

export interface ListChatsOptions {
  search?: string
  before?: string
}

export function listChats(token: string, options: ListChatsOptions = {}): Promise<ChatPage> {
  const params = new URLSearchParams()
  if (options.search) params.set('search', options.search)
  if (options.before) params.set('before', options.before)
  const query = params.toString()
  return apiFetch<ChatPage>(`/chats${query ? `?${query}` : ''}`, {}, token)
}

export interface Message {
  id: string
  chat_id: string
  sender_id: string | null
  sender_type: string
  sender_display_name?: string | null
  sender_avatar_url?: string | null
  source_label: string | null
  client_message_id?: string | null
  visibility?: MessageVisibility
  body: string
  created_at: string
  deleted_at?: string | null
  /** Frontend-only: an optimistic bubble not yet confirmed by the server. Never sent over the wire. */
  pending?: boolean
}

export interface MessagePage {
  messages: Message[]
  next_cursor: string | null
}

export interface ListMessagesOptions {
  before?: string
}

export function listMessages(
  chatId: string,
  token: string,
  options: ListMessagesOptions = {},
): Promise<MessagePage> {
  const params = new URLSearchParams()
  if (options.before) params.set('before', options.before)
  const query = params.toString()
  return apiFetch<MessagePage>(
    `/chats/${chatId}/messages${query ? `?${query}` : ''}`,
    {},
    token,
  )
}

export function sendMessage(
  chatId: string,
  body: string,
  clientMessageId: string,
  token: string,
  visibility: MessageVisibility = 'all',
): Promise<Message> {
  return apiFetch<Message>(
    `/chats/${chatId}/messages`,
    { method: 'POST', body: JSON.stringify({ body, client_message_id: clientMessageId, visibility }) },
    token,
  )
}

export interface MarkRead {
  read_at: string
  message_id?: string
}

export interface ReadState {
  last_read_at: string | null
  last_read_message_id: string | null
}

export function markRead(chatId: string, data: MarkRead, token: string): Promise<ReadState> {
  return apiFetch<ReadState>(
    `/chats/${chatId}/read`,
    { method: 'POST', body: JSON.stringify(data) },
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
