import { useResilientSocket } from '../../../lib/useResilientSocket'

interface UseUserSocketOptions {
  token: string | undefined
  onMessage: () => void
  onUnauthenticated?: () => void
  onReconnect?: () => void
}

export function useUserSocket({
  token,
  onMessage,
  onUnauthenticated,
  onReconnect,
}: UseUserSocketOptions): void {
  useResilientSocket({
    token,
    path: '/websocket/users/me',
    onMessage,
    onUnauthenticated,
    onReconnect,
  })
}
