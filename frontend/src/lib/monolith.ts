import { ApiError, readJsonBody } from './api'

const DEFAULT_MONOLITH_URL = 'http://localhost:3000'

/**
 * Fixed, unlike api.ts's getApiUrl()/getWsUrl(): the chat service's address is what redemption
 * makes dynamic (ADR-0006). The monolith's own address is the one thing every client already
 * has to know in advance, since it's what hands out the exchange code in the first place.
 */
export const MONOLITH_URL =
  (import.meta.env.VITE_MONOLITH_URL as string | undefined) ?? DEFAULT_MONOLITH_URL

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${MONOLITH_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const responseBody = await readJsonBody(response)

  if (!response.ok) {
    throw new ApiError(response.status, responseBody)
  }

  return responseBody as T
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
