import { useEffect } from 'react'
import { API_URL, toWsUrl } from '../../../lib/api'

interface UseConversationSocketOptions {
  conversationId: string
  token: string | undefined
  onMessage: (data: string) => void
  reconnectDelayMs?: number
}

export function useConversationSocket({
  conversationId,
  token,
  onMessage,
  reconnectDelayMs = 2000,
}: UseConversationSocketOptions): void {
  useEffect(() => {
    if (!token) {
      return
    }

    let deliberateClose = false
    let socket: WebSocket
    let reconnectTimer: ReturnType<typeof setTimeout>

    function connect() {
      const url = `${toWsUrl(API_URL)}/websocket/conversations/${conversationId}?token=${token}`
      socket = new WebSocket(url)
      socket.onmessage = (event) => onMessage(event.data)
      socket.onclose = () => {
        if (!deliberateClose) {
          reconnectTimer = setTimeout(connect, reconnectDelayMs)
        }
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
  }, [conversationId, token, onMessage, reconnectDelayMs])
}
