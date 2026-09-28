import { useResilientSocket } from '../../../lib/useResilientSocket'

interface UseChatSocketOptions {
  chatId: string
  token: string | undefined
  onMessage: (data: string) => void
  onRevoked?: () => void
  onUnauthenticated?: () => void
  onReconnect?: () => void
}

export function useChatSocket({
  chatId,
  token,
  onMessage,
  onRevoked,
  onUnauthenticated,
  onReconnect,
}: UseChatSocketOptions): void {
  useResilientSocket({
    token,
    path: `/websocket/chats/${chatId}`,
    onMessage,
    onRevoked,
    onUnauthenticated,
    onReconnect,
  })
}
