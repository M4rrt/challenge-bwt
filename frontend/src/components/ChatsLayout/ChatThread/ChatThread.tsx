import type { KeyboardEvent } from 'react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Divider from '@mui/material/Divider'
import Paper from '@mui/material/Paper'
import TextField from '@mui/material/TextField'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import GroupIcon from '@mui/icons-material/Group'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import PersonIcon from '@mui/icons-material/Person'
import { alpha } from '@mui/material/styles'
import { type Message, getMe, listChats, listMessages, listUsers, sendMessage } from '../../../lib/api'
import { useAuth } from '../../../lib/auth/AuthContext'
import { useChatSocket } from './useChatSocket'
import { chatLabel } from '../chatLabel'
import { setLastSeenAt } from '../lastSeen'
import { groupMessages, type SenderKind } from './messageGrouping'
import { msnButtonSx } from '../msnButtonStyle'
import { skyScrollbarSx } from '../scrollbarStyle'
import { skyTextFieldSx } from '../textFieldStyle'
import { theme } from '../../../theme'

const EXTERNAL_SENDER_TOOLTIP = 'Essa mensagem veio de um serviço externo'

const NAME_COLOR_BY_SENDER_KIND: Record<SenderKind, string> = {
  me: '#075985',
  other: '#047857',
  external: 'warning.dark',
}

const BODY_COLOR_BY_SENDER_KIND: Record<SenderKind, string> = {
  me: 'text.primary',
  other: 'text.primary',
  external: 'warning.dark',
}

const BUBBLE_BG_BY_SENDER_KIND: Record<SenderKind, string> = {
  me: 'rgb(224 242 254 / var(--tw-bg-opacity, 1))',
  other: theme.palette.grey[100],
  external: alpha(theme.palette.warning.main, 0.1),
}

const BUBBLE_BORDER_COLOR_BY_SENDER_KIND: Record<SenderKind, string> = {
  me: 'rgb(125 211 252 / var(--tw-border-opacity, 1))',
  other: theme.palette.divider,
  external: theme.palette.warning.light,
}

function upsertMessage(queryClient: QueryClient, chatId: string, message: Message) {
  queryClient.setQueryData<Message[]>(['messages', chatId], (current = []) =>
    current.some((existing) => existing.id === message.id) ? current : [...current, message],
  )
}

const SCROLL_BOTTOM_THRESHOLD_PX = 40

function ChatThread() {
  const { chatId } = useParams<{ chatId: string }>()
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
  const chatsQuery = useQuery({
    queryKey: ['chats'],
    queryFn: () => listChats(token!),
    enabled: !!token,
  })
  const messagesQuery = useQuery({
    queryKey: ['messages', chatId],
    queryFn: () => listMessages(chatId!, token!),
    enabled: !!token && !!chatId,
  })

  const sendMutation = useMutation({
    mutationFn: (body: string) => sendMessage(chatId!, body, token!),
    onSuccess: (message) => {
      upsertMessage(queryClient, chatId!, message)
    },
  })

  const handleSocketMessage = useCallback(
    (data: string) => {
      const message = JSON.parse(data) as Message
      upsertMessage(queryClient, chatId!, message)
    },
    [queryClient, chatId],
  )

  useChatSocket({
    chatId: chatId!,
    token,
    onMessage: handleSocketMessage,
  })

  const messages = messagesQuery.data ?? []

  const latestMessagesRef = useRef<Message[]>(messages)
  useEffect(() => {
    latestMessagesRef.current = messagesQuery.data ?? []
  }, [messagesQuery.data])

  useEffect(() => {
    const meId = meQuery.data?.id
    if (!meId || !chatId) return

    function recordLastSeen() {
      const lastMessage = latestMessagesRef.current.at(-1)
      setLastSeenAt(meId!, chatId!, lastMessage?.created_at ?? null)
    }

    recordLastSeen()
    return recordLastSeen
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meQuery.data?.id, chatId])

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
  const chat = chatsQuery.data?.find((c) => c.id === chatId)
  const title = chat ? chatLabel(chat, meQuery.data?.id, usernameById) : undefined
  const isGroup = (chat?.participant_user_ids.length ?? 0) > 2

  return (
    <Paper
      elevation={0}
      sx={{ flex: 1, display: 'flex', flexDirection: 'column', position: 'relative', borderRadius: 0.5 }}
    >
      {title && (
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1.5,
            px: 2,
            py: 1.5,
            borderBottom: 1,
            borderColor: 'divider',
            background: 'linear-gradient(to right, rgb(224 242 254 / 0.8), rgb(255 255 255 / 0))',
          }}
        >
          <Box
            sx={{
              width: 40,
              height: 40,
              borderRadius: '8px',
              border: '2px solid',
              borderColor: 'primary.main',
              bgcolor: 'primary.light',
              boxShadow: 'inset 0 0 0 2px rgb(255 255 255 / 0.6)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            {isGroup ? (
              <GroupIcon aria-label="Chat em grupo" sx={{ color: 'primary.contrastText' }} />
            ) : (
              <PersonIcon aria-label="Chat individual" sx={{ color: 'primary.contrastText' }} />
            )}
          </Box>
          <Typography variant="h6">{title}</Typography>
        </Box>
      )}
      <Box ref={listRef} onScroll={handleScroll} sx={{ flex: 1, overflowY: 'auto', pl: 2, pt: 2, ...skyScrollbarSx }}>
        {groups.map((group) => (
          <Box
            key={group.messages[0].id}
            sx={{
              mb: 1.5,
              maxWidth: '75%',
              bgcolor: BUBBLE_BG_BY_SENDER_KIND[group.senderKind],
              border: 1,
              borderColor: BUBBLE_BORDER_COLOR_BY_SENDER_KIND[group.senderKind],
              borderRadius: '3px',
              px: 2,
              py: 1,
            }}
          >
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 1, mb: 1 }}>
              <Typography
                variant="body1"
                sx={{ color: NAME_COLOR_BY_SENDER_KIND[group.senderKind], display: 'inline-flex', alignItems: 'center', gap: 0.5, lineHeight: 1 }}
              >
                {group.displayName}:
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
              <Typography variant="caption" sx={{ color: 'text.secondary', flexShrink: 0 }}>
                {group.timestamp}
              </Typography>
            </Box>
            <Divider sx={{ mb: 1 }} />
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
      <Box
        sx={{
          display: 'flex',
          gap: 1,
          p: 1,
          borderRadius: 0,
          border: 1,
          borderColor: 'rgb(125 211 252 / var(--tw-border-opacity, 1))',
          bgcolor: 'rgb(224 242 254 / 0.5)',
        }}
      >
        <TextField
          fullWidth
          multiline
          maxRows={4}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Adicione sua mensagem aqui"
          sx={skyTextFieldSx}
        />
        <Button variant="contained" onClick={submitMessage} sx={msnButtonSx}>
          Enviar
        </Button>
      </Box>
    </Paper>
  )
}

export default ChatThread
