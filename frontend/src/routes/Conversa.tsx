import type { KeyboardEvent } from 'react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Paper from '@mui/material/Paper'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { type Message, listMessages, listUsers, sendMessage } from '../lib/api'
import { useAuth } from '../lib/auth/AuthContext'
import { useConversationSocket } from '../lib/useConversationSocket'
import { groupMessages } from '../lib/messageGrouping'

function upsertMessage(queryClient: QueryClient, conversationId: string, message: Message) {
  queryClient.setQueryData<Message[]>(['messages', conversationId], (current = []) =>
    current.some((existing) => existing.id === message.id) ? current : [...current, message],
  )
}

const SCROLL_BOTTOM_THRESHOLD_PX = 40

function Conversa() {
  const { conversationId } = useParams<{ conversationId: string }>()
  const auth = useAuth()
  const token = auth.token ?? undefined
  const queryClient = useQueryClient()

  const [input, setInput] = useState('')
  const [hasNewMessages, setHasNewMessages] = useState(false)
  const isAtBottomRef = useRef(true)
  const listRef = useRef<HTMLDivElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const usersQuery = useQuery({
    queryKey: ['users'],
    queryFn: () => listUsers(token!),
    enabled: !!token,
  })
  const messagesQuery = useQuery({
    queryKey: ['messages', conversationId],
    queryFn: () => listMessages(conversationId!, token!),
    enabled: !!token && !!conversationId,
  })

  const sendMutation = useMutation({
    mutationFn: (body: string) => sendMessage(conversationId!, body, token!),
    onSuccess: (message) => {
      upsertMessage(queryClient, conversationId!, message)
    },
  })

  const handleSocketMessage = useCallback(
    (data: string) => {
      const message = JSON.parse(data) as Message
      upsertMessage(queryClient, conversationId!, message)
    },
    [queryClient, conversationId],
  )

  useConversationSocket({
    conversationId: conversationId!,
    token,
    onMessage: handleSocketMessage,
  })

  const messages = messagesQuery.data ?? []

  useEffect(() => {
    if (isAtBottomRef.current) {
      bottomRef.current?.scrollIntoView()
      setHasNewMessages(false)
    } else if (messages.length > 0) {
      setHasNewMessages(true)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages.length])

  function handleScroll() {
    const el = listRef.current
    if (!el) return
    isAtBottomRef.current =
      el.scrollHeight - el.scrollTop - el.clientHeight < SCROLL_BOTTOM_THRESHOLD_PX
  }

  function scrollToBottom() {
    bottomRef.current?.scrollIntoView()
    isAtBottomRef.current = true
    setHasNewMessages(false)
  }

  function submitMessage() {
    const body = input.trim()
    if (!body) return
    sendMutation.mutate(body)
    setInput('')
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submitMessage()
    }
  }

  const usernameById = new Map(usersQuery.data?.map((user) => [user.id, user.username]) ?? [])
  const groups = groupMessages(messages, usernameById)

  return (
    <Paper
      elevation={0}
      sx={{ flex: 1, display: 'flex', flexDirection: 'column', p: 2, gap: 2, position: 'relative' }}
    >
      <Box ref={listRef} onScroll={handleScroll} sx={{ flex: 1, overflowY: 'auto' }}>
        {groups.map((group) => (
          <Box key={group.messages[0].id} sx={{ mb: 2 }}>
            <Typography variant="caption" color="text.secondary">
              {group.displayName} · {group.timestamp}
            </Typography>
            {group.messages.map((message) => (
              <Typography key={message.id}>{message.body}</Typography>
            ))}
          </Box>
        ))}
        <div ref={bottomRef} />
      </Box>
      {hasNewMessages && (
        <Chip
          label="Novas mensagens ↓"
          color="primary"
          onClick={scrollToBottom}
          sx={{ alignSelf: 'center', position: 'absolute', bottom: 80, left: '50%', transform: 'translateX(-50%)' }}
        />
      )}
      <Box sx={{ display: 'flex', gap: 1 }}>
        <TextField
          fullWidth
          multiline
          maxRows={4}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={handleKeyDown}
        />
        <Button variant="contained" onClick={submitMessage}>
          Enviar
        </Button>
      </Box>
    </Paper>
  )
}

export default Conversa
