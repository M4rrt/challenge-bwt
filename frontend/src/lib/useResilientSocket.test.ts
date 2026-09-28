import { renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { refreshToken } from './api'
import { useResilientSocket } from './useResilientSocket'

vi.mock('./api', async () => {
  const actual = await vi.importActual<typeof import('./api')>('./api')
  return { ...actual, refreshToken: vi.fn() }
})

class FakeWebSocket {
  static instances: FakeWebSocket[] = []
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSING = 2
  static readonly CLOSED = 3

  url: string
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: ((event: { code: number }) => void) | null = null
  sent: string[] = []
  readyState: number = FakeWebSocket.CONNECTING

  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }

  open() {
    this.readyState = FakeWebSocket.OPEN
    this.onopen?.()
  }

  send(data: string) {
    this.sent.push(data)
  }

  close() {
    this.readyState = FakeWebSocket.CLOSED
  }

  addEventListener() {
    // Only used by the hook's cleanup path for a socket still mid-handshake; irrelevant here.
  }

  receive(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) })
  }

  closeWithCode(code: number) {
    this.readyState = FakeWebSocket.CLOSED
    this.onclose?.({ code })
  }
}

function latestSocket(): FakeWebSocket {
  return FakeWebSocket.instances[FakeWebSocket.instances.length - 1]
}

beforeEach(() => {
  FakeWebSocket.instances = []
  vi.stubGlobal('WebSocket', FakeWebSocket)
  vi.mocked(refreshToken).mockReset()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('useResilientSocket', () => {
  it('connects to the given path with the token as a query param', () => {
    renderHook(() =>
      useResilientSocket({ token: 'token-123', path: '/websocket/chats/chat-1', onMessage: vi.fn() }),
    )

    expect(latestSocket().url).toContain('/websocket/chats/chat-1?token=token-123')
  })

  it('forwards a frame with no recognized type as a message', () => {
    const onMessage = vi.fn()
    renderHook(() => useResilientSocket({ token: 'token-123', path: '/ws', onMessage }))
    latestSocket().open()

    latestSocket().receive({ id: 'msg-1', body: 'oi' })

    expect(onMessage).toHaveBeenCalledWith(JSON.stringify({ id: 'msg-1', body: 'oi' }))
  })

  it.each(['presence.snapshot', 'presence.online', 'presence.offline', 'typing', 'token.renewed'])(
    'does not forward a %s control frame as a message',
    (type) => {
      const onMessage = vi.fn()
      renderHook(() => useResilientSocket({ token: 'token-123', path: '/ws', onMessage }))
      latestSocket().open()

      latestSocket().receive({ type })

      expect(onMessage).not.toHaveBeenCalled()
    },
  )

  it('on token.expiring, fetches a fresh token and sends it back over the same socket, opening no new one', async () => {
    vi.mocked(refreshToken).mockResolvedValue('fresh-token')
    renderHook(() => useResilientSocket({ token: 'token-123', path: '/ws', onMessage: vi.fn() }))
    latestSocket().open()
    const socket = latestSocket()

    socket.receive({ type: 'token.expiring' })
    await vi.waitFor(() => expect(socket.sent).toHaveLength(1))

    expect(socket.sent[0]).toBe(JSON.stringify({ type: 'token.renew', token: 'fresh-token' }))
    expect(FakeWebSocket.instances).toHaveLength(1)
  })

  it('on ACCESS_REVOKED (4403), calls onRevoked and does not reconnect', async () => {
    vi.useFakeTimers()
    const onRevoked = vi.fn()
    renderHook(() =>
      useResilientSocket({ token: 'token-123', path: '/ws', onMessage: vi.fn(), onRevoked }),
    )
    latestSocket().open()

    latestSocket().closeWithCode(4403)
    await vi.advanceTimersByTimeAsync(30000)

    expect(onRevoked).toHaveBeenCalledTimes(1)
    expect(FakeWebSocket.instances).toHaveLength(1)
  })

  it('on UNAUTHENTICATED (1008), calls onUnauthenticated and does not reconnect', async () => {
    vi.useFakeTimers()
    const onUnauthenticated = vi.fn()
    renderHook(() =>
      useResilientSocket({ token: 'token-123', path: '/ws', onMessage: vi.fn(), onUnauthenticated }),
    )
    latestSocket().open()

    latestSocket().closeWithCode(1008)
    await vi.advanceTimersByTimeAsync(30000)

    expect(onUnauthenticated).toHaveBeenCalledTimes(1)
    expect(FakeWebSocket.instances).toHaveLength(1)
  })

  it('on TOKEN_EXPIRED (4401), fetches a fresh token and reconnects promptly with it', async () => {
    vi.mocked(refreshToken).mockResolvedValue('fresh-token')
    renderHook(() => useResilientSocket({ token: 'token-123', path: '/ws', onMessage: vi.fn() }))
    latestSocket().open()

    latestSocket().closeWithCode(4401)
    await vi.waitFor(() => expect(FakeWebSocket.instances).toHaveLength(2))

    expect(latestSocket().url).toContain('token=fresh-token')
  })

  it('on an unrecognized close code, reconnects after a backoff delay without calling onRevoked/onUnauthenticated', async () => {
    vi.useFakeTimers()
    const onRevoked = vi.fn()
    const onUnauthenticated = vi.fn()
    renderHook(() =>
      useResilientSocket({
        token: 'token-123',
        path: '/ws',
        onMessage: vi.fn(),
        onRevoked,
        onUnauthenticated,
      }),
    )
    latestSocket().open()

    latestSocket().closeWithCode(1006)
    expect(FakeWebSocket.instances).toHaveLength(1)

    await vi.advanceTimersByTimeAsync(2000)

    expect(FakeWebSocket.instances).toHaveLength(2)
    expect(onRevoked).not.toHaveBeenCalled()
    expect(onUnauthenticated).not.toHaveBeenCalled()
  })

  it('does not open a new socket from a TOKEN_EXPIRED refresh that resolves after the component has already unmounted', async () => {
    let resolveRefresh: (token: string) => void = () => {}
    vi.mocked(refreshToken).mockReturnValue(
      new Promise((resolve) => {
        resolveRefresh = resolve
      }),
    )
    const { unmount } = renderHook(() =>
      useResilientSocket({ token: 'token-123', path: '/ws', onMessage: vi.fn() }),
    )
    latestSocket().open()

    latestSocket().closeWithCode(4401)
    unmount()
    resolveRefresh('fresh-token')
    await vi.waitFor(() => expect(refreshToken).toHaveBeenCalledTimes(1))

    expect(FakeWebSocket.instances).toHaveLength(1)
  })

  it('calls onReconnect after a successful reconnect, but not after the initial connection', async () => {
    vi.useFakeTimers()
    const onReconnect = vi.fn()
    renderHook(() =>
      useResilientSocket({ token: 'token-123', path: '/ws', onMessage: vi.fn(), onReconnect }),
    )
    latestSocket().open()
    expect(onReconnect).not.toHaveBeenCalled()

    latestSocket().closeWithCode(1006)
    await vi.advanceTimersByTimeAsync(2000)
    latestSocket().open()

    expect(onReconnect).toHaveBeenCalledTimes(1)
  })
})
