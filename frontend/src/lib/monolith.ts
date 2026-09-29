import { ApiError, readJsonBody } from './api'

// The Django monolith. Not :3000, which is the BWT frontend's own dev server.
const DEFAULT_MONOLITH_URL = 'http://localhost:8000'

/**
 * Fixed, unlike api.ts's getApiUrl()/getWsUrl(): the chat service's address is what redemption
 * makes dynamic (ADR-0006). The monolith's own address is the one thing every client already
 * has to know in advance, since it's what hands out the exchange code in the first place.
 */
export const MONOLITH_URL =
  (import.meta.env.VITE_MONOLITH_URL as string | undefined) ?? DEFAULT_MONOLITH_URL

async function request<T>(path: string, options: RequestInit, renewalToken?: string): Promise<T> {
  const response = await fetch(`${MONOLITH_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(renewalToken ? { Authorization: `Bearer ${renewalToken}` } : {}),
    },
  })
  const responseBody = await readJsonBody(response)

  if (!response.ok) {
    throw new ApiError(response.status, responseBody)
  }

  return responseBody as T
}

function postJson<T>(path: string, body: unknown, renewalToken?: string): Promise<T> {
  return request<T>(path, { method: 'POST', body: JSON.stringify(body) }, renewalToken)
}

function getJson<T>(path: string, renewalToken: string): Promise<T> {
  return request<T>(path, { method: 'GET' }, renewalToken)
}

export interface SessionRedemption {
  renewal_token: string
  api_url: string
  ws_url: string
}

/** Single-use, short-lived exchange code from the URL fragment, redeemed for a chat-scoped renewal credential. */
export function redeemExchangeCode(code: string): Promise<SessionRedemption> {
  return postJson<SessionRedemption>('/chat/sessions/redeem', { code })
}

export interface ChatTokenResponse {
  access_token: string
  token_type: string
}

/** Exchanges the renewal credential for a fifteen-minute chat token — the same call for the first token and every renewal. */
export function issueChatToken(renewalToken: string): Promise<ChatTokenResponse> {
  return postJson<ChatTokenResponse>('/chat/sessions/token', { renewal_token: renewalToken })
}

export interface Contact {
  id: string
  display_name: string
  avatar_url: string | null
  kind: 'staff' | 'client'
}

/**
 * Assumed contract (ticket 22, unconfirmed against the real monolith — see that ticket's comments):
 * `GET {MONOLITH_URL}/chat/contacts?search=` -> the staff/CRM-contact list a Chat may be started
 * with, authenticated with the renewal credential from session handoff, same as `createChat`.
 */
export function listContacts(renewalToken: string, search?: string): Promise<Contact[]> {
  const params = new URLSearchParams()
  if (search) params.set('search', search)
  const query = params.toString()
  return getJson<Contact[]>(`/chat/contacts${query ? `?${query}` : ''}`, renewalToken)
}

export interface CreateChatResponse {
  chat_id: string
}

/**
 * Assumed contract (ticket 22, unconfirmed against the real monolith — see that ticket's comments):
 * `POST {MONOLITH_URL}/chat/chats { participant_ids, name? }` -> `{ chat_id }`. `participant_ids`
 * never includes the caller — the monolith adds the acting user itself, the same split the internal
 * composition command already makes. Authenticated with the renewal credential in the `Authorization`
 * header, since the request body's shape is already fixed by the ticket's contract.
 */
export function createChat(
  renewalToken: string,
  participantIds: string[],
  name?: string,
): Promise<CreateChatResponse> {
  return postJson<CreateChatResponse>(
    '/chat/chats',
    name ? { participant_ids: participantIds, name } : { participant_ids: participantIds },
    renewalToken,
  )
}
