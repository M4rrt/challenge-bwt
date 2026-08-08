import { useEffect } from 'react'
import { API_URL, toWsUrl } from './api'

interface UseUserSocketOptions {
  token: string | undefined
  onMessage: () => void
  reconnectDelayMs?: number
}

export function useUserSocket({ token, onMessage, reconnectDelayMs = 2000 }: UseUserSocketOptions): void {
  useEffect(() => {
    if (!token) {
      return
    }

    let deliberateClose = false
    let socket: WebSocket
    let reconnectTimer: ReturnType<typeof setTimeout>

    function connect() {
      const url = `${toWsUrl(API_URL)}/websocket/users/me?token=${token}`
      socket = new WebSocket(url)
      socket.onmessage = () => onMessage()
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
      socket.close()
    }
  }, [token, onMessage, reconnectDelayMs])
}
