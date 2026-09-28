import { decodeJwt } from 'jose'

const CHAT_CLAIM_NAMESPACE = 'https://brwinetours.com/chat'

export function isTokenExpired(token: string): boolean {
  try {
    const { exp } = decodeJwt(token)
    if (!exp) {
      return false
    }
    return exp * 1000 <= Date.now()
  } catch {
    return true
  }
}

export function getUserId(token: string): string | null {
  try {
    const sub = decodeJwt(token).sub
    return typeof sub === 'string' ? sub : null
  } catch {
    return null
  }
}

export type UserKind = 'staff' | 'client'

export function getUserKind(token: string): UserKind | null {
  try {
    const claims = decodeJwt(token)[CHAT_CLAIM_NAMESPACE]
    if (!claims || typeof claims !== 'object') {
      return null
    }
    const userKind = (claims as { user_kind?: unknown }).user_kind
    return userKind === 'staff' || userKind === 'client' ? userKind : null
  } catch {
    return null
  }
}
