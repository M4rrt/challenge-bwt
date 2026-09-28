import { useEffect, useRef } from 'react'
import { getWsUrl, refreshToken } from './api'

/**
 * The three closures `app/core/close_codes.py` defines, and nothing else: a
 * network failure is deliberately not one of these (see that module's
 * docstring) and falls through to backoff below.
 */
const UNAUTHENTICATED = 1008
const TOKEN_EXPIRED = 4401
const ACCESS_REVOKED = 4403

const EXPIRING = 'token.expiring'
const RENEW = 'token.renew'

/** Frame types the connection protocol defines that are not a Message/summary payload — see `app/services/connection.py` and `app/services/presence.py`. */
const CONTROL_FRAME_TYPES = new Set([
  'token.expiring',
  'token.renewed',
  'presence.snapshot',
  'presence.online',
  'presence.offline',
  'typing',
])

const INITIAL_BACKOFF_MS = 1000
const MAX_BACKOFF_MS = 16000

interface ControlFrame {
  type: string
}

function asControlFrame(data: string): ControlFrame | null {
  try {
    const parsed = JSON.parse(data) as unknown
    if (parsed && typeof parsed === 'object' && typeof (parsed as ControlFrame).type === 'string') {
      return parsed as ControlFrame
    }
  } catch {
    // Not JSON, or not an object — never a control frame, always forwarded as a message below.
  }
  return null
}

interface UseResilientSocketOptions {
  /** `undefined` means "not authenticated yet" — no connection is attempted. */
  token: string | undefined
  /** The path after the service's WS host, e.g. `/websocket/chats/{chatId}` — stable for the socket's lifetime; a changed path tears down and reconnects. */
  path: string
  /** A payload frame (anything without a recognized `type`) as raw JSON text, exactly as it arrived. */
  onMessage: (data: string) => void
  /** ACCESS_REVOKED: this Chat is no longer the caller's. Does not retry. */
  onRevoked?: () => void
  /** UNAUTHENTICATED, or a token refresh that itself failed: the credential is no good here. Does not retry. */
  onUnauthenticated?: () => void
  /** Fired after every reconnect (not the first connection) — the caller's cue to resync anything missed while disconnected. */
  onReconnect?: () => void
}

export function useResilientSocket({
  token,
  path,
  onMessage,
  onRevoked,
  onUnauthenticated,
  onReconnect,
}: UseResilientSocketOptions): void {
  const tokenRef = useRef(token)
  useEffect(() => {
    tokenRef.current = token
  }, [token])

  const callbacksRef = useRef({ onMessage, onRevoked, onUnauthenticated, onReconnect })
  useEffect(() => {
    callbacksRef.current = { onMessage, onRevoked, onUnauthenticated, onReconnect }
  })

  // Deliberately keyed on presence-of-token and path, not on the token string itself: the
  // socket renews its own credential in band (see `connect` below) and must not be torn
  // down and reopened by React just because that renewal changed the token elsewhere.
  const hasToken = token !== undefined
  useEffect(() => {
    if (!hasToken) {
      return
    }

    let deliberateClose = false
    let socket: WebSocket
    let reconnectTimer: ReturnType<typeof setTimeout>
    let backoffMs = INITIAL_BACKOFF_MS
    let hasConnectedOnce = false

    function connect(overrideToken?: string) {
      const activeToken = overrideToken ?? tokenRef.current
      if (!activeToken) {
        return
      }
      socket = new WebSocket(`${getWsUrl()}${path}?token=${activeToken}`)

      socket.onopen = () => {
        backoffMs = INITIAL_BACKOFF_MS
        if (hasConnectedOnce) {
          callbacksRef.current.onReconnect?.()
        }
        hasConnectedOnce = true
      }

      socket.onmessage = (event) => {
        const frame = asControlFrame(event.data)
        if (frame?.type === EXPIRING) {
          refreshToken()
            .then((newToken) => {
              if (deliberateClose) {
                return
              }
              tokenRef.current = newToken
              socket.send(JSON.stringify({ type: RENEW, token: newToken }))
            })
            .catch(() => {
              // The socket is still open on the old credential; a close will follow on its
              // own schedule (TOKEN_EXPIRED) and retries the refresh from there.
            })
          return
        }
        if (frame && CONTROL_FRAME_TYPES.has(frame.type)) {
          return
        }
        callbacksRef.current.onMessage(event.data)
      }

      socket.onclose = (event) => {
        if (deliberateClose) {
          return
        }
        if (event.code === ACCESS_REVOKED) {
          callbacksRef.current.onRevoked?.()
          return
        }
        if (event.code === UNAUTHENTICATED) {
          callbacksRef.current.onUnauthenticated?.()
          return
        }
        if (event.code === TOKEN_EXPIRED) {
          refreshToken()
            .then((newToken) => {
              if (deliberateClose) {
                return
              }
              tokenRef.current = newToken
              connect(newToken)
            })
            .catch(() => {
              if (!deliberateClose) {
                callbacksRef.current.onUnauthenticated?.()
              }
            })
          return
        }
        const delay = backoffMs
        backoffMs = Math.min(backoffMs * 2, MAX_BACKOFF_MS)
        reconnectTimer = setTimeout(() => connect(), delay)
      }
    }

    connect()

    return () => {
      deliberateClose = true
      clearTimeout(reconnectTimer)
      if (socket.readyState === WebSocket.OPEN) {
        socket.close()
      } else if (socket.readyState === WebSocket.CONNECTING) {
        socket.addEventListener('open', () => socket.close(), { once: true })
      }
    }
  }, [hasToken, path])
}
