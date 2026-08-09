import { decodeJwt } from 'jose'

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
