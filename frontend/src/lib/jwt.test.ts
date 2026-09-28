import { describe, expect, it } from 'vitest'
import { getUserId, getUserKind, isTokenExpired } from './jwt'

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

describe('getUserKind', () => {
  it("reads the user_kind claim from the chat claim namespace", () => {
    const token = makeJwt({
      sub: 'user-1',
      'https://brwinetours.com/chat': { user_kind: 'staff' },
    })

    expect(getUserKind(token)).toBe('staff')
  })

  it('returns null when the token carries no chat claims', () => {
    const token = makeJwt({ sub: 'user-1' })

    expect(getUserKind(token)).toBeNull()
  })

  it('returns null for a malformed token', () => {
    expect(getUserKind('not-a-real-token')).toBeNull()
  })
})

describe('getUserId', () => {
  it('reads the sub claim as the caller id', () => {
    const token = makeJwt({ sub: 'user-1' })

    expect(getUserId(token)).toBe('user-1')
  })

  it('returns null for a malformed token', () => {
    expect(getUserId('not-a-real-token')).toBeNull()
  })

  it('returns null when sub is missing', () => {
    const token = makeJwt({})

    expect(getUserId(token)).toBeNull()
  })
})
