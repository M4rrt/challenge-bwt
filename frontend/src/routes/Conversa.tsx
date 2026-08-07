import type { KeyboardEvent } from 'react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Paper from '@mui/material/Paper'
import TextField from '@mui/material/TextField'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import { type Message, getMe, listMessages, listUsers, sendMessage } from '../lib/api'
import { useAuth } from '../lib/auth/AuthContext'
import { useConversationSocket } from '../lib/useConversationSocket'
import { groupMessages, type SenderKind } from '../lib/messageGrouping'

const EXTERNAL_SENDER_TOOLTIP = 'Essa mensagem veio de um serviço externo'

const NAME_COLOR_BY_SENDER_KIND: Record<SenderKind, string> = {
  me: 'text.primary',
  other: 'primary.main',
  external: 'warning.dark',
}

const BODY_COLOR_BY_SENDER_KIND: Record<SenderKind, string> = {
  me: 'text.primary',
  other: 'text.primary',
  external: 'warning.dark',
}

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

  const meQuery = useQuery({ queryKey: ['me'], queryFn: () => getMe(token!), enabled: !!token })
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
  const groups = groupMessages(messages, usernameById, meQuery.data?.id)

  return (
    <Paper
      elevation={0}
      sx={{ flex: 1, display: 'flex', flexDirection: 'column', p: 2, gap: 2, position: 'relative' }}
    >
      <Box ref={listRef} onScroll={handleScroll} sx={{ flex: 1, overflowY: 'auto' }}>
        {groups.map((group) => (
          <Box key={group.messages[0].id} sx={{ mb: 2 }}>
            <Typography
              variant="caption"
              sx={{ color: NAME_COLOR_BY_SENDER_KIND[group.senderKind], display: 'inline-flex', alignItems: 'center', gap: 0.5 }}
            >
              {group.displayName} · {group.timestamp}
              {group.senderKind === 'external' && (
                <Tooltip title={EXTERNAL_SENDER_TOOLTIP}>
                  <InfoOutlinedIcon
                    aria-label={EXTERNAL_SENDER_TOOLTIP}
                    fontSize="inherit"
                    sx={{ color: 'warning.dark' }}
                  />
                </Tooltip>
              )}
            </Typography>
            {group.messages.map((message) => (
              <Typography
                key={message.id}
                data-sender-kind={group.senderKind}
                sx={{ color: BODY_COLOR_BY_SENDER_KIND[group.senderKind] }}
              >
                {message.body}
              </Typography>
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
