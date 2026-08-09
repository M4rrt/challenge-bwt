import { describe, expect, it } from 'vitest'
import { isTokenExpired } from './jwt'

function makeJwt(payload: Record<string, unknown>): string {
  const encode = (value: unknown) =>
    btoa(JSON.stringify(value)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  return `${encode({ alg: 'HS256', typ: 'JWT' })}.${encode(payload)}.fake-signature`
}

describe('isTokenExpired', () => {
  it('returns true for a token whose exp is in the past', () => {
    const token = makeJwt({ exp: Math.floor(Date.now() / 1000) - 60 })

    expect(isTokenExpired(token)).toBe(true)
  })

  it('returns false for a token whose exp is in the future', () => {
    const token = makeJwt({ exp: Math.floor(Date.now() / 1000) + 3600 })

    expect(isTokenExpired(token)).toBe(false)
  })

  it('returns true for a malformed token', () => {
    expect(isTokenExpired('not-a-real-token')).toBe(true)
  })
})
