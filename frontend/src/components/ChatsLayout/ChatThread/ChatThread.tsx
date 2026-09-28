import type { KeyboardEvent } from 'react'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import {
  type InfiniteData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Checkbox from '@mui/material/Checkbox'
import Chip from '@mui/material/Chip'
import Divider from '@mui/material/Divider'
import FormControlLabel from '@mui/material/FormControlLabel'
import Paper from '@mui/material/Paper'
import TextField from '@mui/material/TextField'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import GroupIcon from '@mui/icons-material/Group'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import PersonIcon from '@mui/icons-material/Person'
import { alpha } from '@mui/material/styles'
import {
  type Message,
  type MessagePage,
  type MessageVisibility,
  getMe,
  listChats,
  listMessages,
  markRead,
  sendMessage,
} from '../../../lib/api'
import { getUserId, getUserKind } from '../../../lib/jwt'
import { useAuth } from '../../../lib/auth/AuthContext'
import { useChatSocket } from './useChatSocket'
import { chatLabel } from '../chatLabel'
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

const STAFF_ONLY_BUBBLE_BG = alpha(theme.palette.secondary.main, 0.12)
const STAFF_ONLY_BORDER_COLOR = theme.palette.secondary.light

const SCROLL_BOTTOM_THRESHOLD_PX = 40
const SCROLL_TOP_THRESHOLD_PX = 40

function messagesOf(data: InfiniteData<MessagePage> | undefined): Message[] {
  if (!data) return []
  return [...data.pages].reverse().flatMap((page) => page.messages)
}

function ChatThread() {
  const { chatId } = useParams<{ chatId: string }>()
  const auth = useAuth()
  const navigate = useNavigate()
  const token = auth.token ?? undefined
  const queryClient = useQueryClient()

  const [input, setInput] = useState('')
  const [staffOnly, setStaffOnly] = useState(false)
  const [hasNewMessages, setHasNewMessages] = useState(false)
  const isAtBottomRef = useRef(true)
  const listRef = useRef<HTMLDivElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const prevScrollHeightRef = useRef<number | null>(null)

  const meQuery = useQuery({ queryKey: ['me'], queryFn: () => getMe(token!), enabled: !!token })
  // The token's own `sub` claim, decoded synchronously — a fallback for the brief window before
  // getMe resolves, so an optimistic bubble sent right after opening a chat isn't misattributed
  // to an external sender for lack of a resolved profile.
  const currentUserId = meQuery.data?.id ?? (token ? (getUserId(token) ?? undefined) : undefined)
  const chatsQuery = useInfiniteQuery({
    queryKey: ['chats', ''],
    queryFn: ({ pageParam }: { pageParam: string | undefined }) =>
      listChats(token!, { before: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: !!token,
  })
  const messagesQuery = useInfiniteQuery({
    queryKey: ['messages', chatId],
    queryFn: ({ pageParam }: { pageParam: string | undefined }) =>
      listMessages(chatId!, token!, { before: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: !!token && !!chatId,
  })

  function updateNewestPage(update: (messages: Message[]) => Message[]) {
    queryClient.setQueryData<InfiniteData<MessagePage>>(['messages', chatId], (current) => {
      if (!current || current.pages.length === 0) return current
      const pages = [...current.pages]
      pages[0] = { ...pages[0], messages: update(pages[0].messages) }
      return { ...current, pages }
    })
  }

  function upsertConfirmed(message: Message) {
    updateNewestPage((messages) => {
      const pendingIndex = messages.findIndex(
        (existing) =>
          existing.pending &&
          existing.client_message_id &&
          existing.client_message_id === message.client_message_id,
      )
      if (pendingIndex !== -1) {
        const next = [...messages]
        next[pendingIndex] = message
        return next
      }
      if (messages.some((existing) => existing.id === message.id)) {
        return messages
      }
      return [...messages, message]
    })
  }

  const sendMutation = useMutation({
    mutationFn: (vars: { body: string; clientMessageId: string; visibility: MessageVisibility }) =>
      sendMessage(chatId!, vars.body, vars.clientMessageId, token!, vars.visibility),
    onSuccess: (message) => upsertConfirmed(message),
    onError: (_error, vars) => {
      updateNewestPage((messages) =>
        messages.filter((existing) => existing.client_message_id !== vars.clientMessageId),
      )
      // Only restore into an still-empty box: the user may already be typing a follow-up
      // message, and a failure landing later must not overwrite it with the old, failed text.
      setInput((current) => (current === '' ? vars.body : current))
    },
  })

  const markReadMutation = useMutation({
    // chatId/token travel through vars rather than this closure: mutate() can be called from a
    // stale effect-cleanup closure (leaving a chat) after chatId has already changed, and
    // useMutation rebinds mutationFn to the latest render on every render — reading chatId here
    // would attribute the outgoing chat's read-mark to the chat just navigated to instead.
    mutationFn: (vars: { chatId: string; token: string; readAt: string; messageId?: string }) =>
      markRead(vars.chatId, { read_at: vars.readAt, message_id: vars.messageId }, vars.token),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['chats'] }),
  })

  function handleSocketMessage(data: string) {
    upsertConfirmed(JSON.parse(data) as Message)
  }

  function handleRevoked() {
    queryClient.invalidateQueries({ queryKey: ['chats'] })
    navigate('/chats')
  }

  function handleUnauthenticated() {
    auth.logout()
    navigate('/')
  }

  function handleChatReconnect() {
    queryClient.invalidateQueries({ queryKey: ['messages', chatId] })
  }

  useChatSocket({
    chatId: chatId!,
    token,
    onMessage: handleSocketMessage,
    onRevoked: handleRevoked,
    onUnauthenticated: handleUnauthenticated,
    onReconnect: handleChatReconnect,
  })

  const messages = messagesOf(messagesQuery.data)

  const latestMessagesRef = useRef<Message[]>(messages)
  useEffect(() => {
    latestMessagesRef.current = messages
  })

  const hasMarkedOpenRef = useRef(false)
  useEffect(() => {
    hasMarkedOpenRef.current = false
  }, [chatId])

  useEffect(() => {
    if (!token || !chatId || hasMarkedOpenRef.current || messagesQuery.data === undefined) {
      return
    }
    hasMarkedOpenRef.current = true
    markReadMutation.mutate({
      chatId,
      token,
      readAt: new Date().toISOString(),
      messageId: latestMessagesRef.current.at(-1)?.id,
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, chatId, messagesQuery.data])

  useEffect(() => {
    if (!token || !chatId) return
    return () => {
      markReadMutation.mutate({
        chatId,
        token,
        readAt: new Date().toISOString(),
        messageId: latestMessagesRef.current.at(-1)?.id,
      })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, chatId])

  useEffect(() => {
    if (isAtBottomRef.current) {
      bottomRef.current?.scrollIntoView()
      setHasNewMessages(false)
    } else if (messages.length > 0) {
      setHasNewMessages(true)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages.length])

  const wasFetchingNextPageRef = useRef(false)
  useLayoutEffect(() => {
    // Keyed on the fetch settling (success or failure), not on the page count: a failed
    // fetchNextPage() never changes pages.length, which would otherwise leave a stale
    // prevScrollHeightRef around to corrupt the scroll-restoration math on the next attempt.
    if (wasFetchingNextPageRef.current && !messagesQuery.isFetchingNextPage) {
      const el = listRef.current
      if (el && prevScrollHeightRef.current !== null) {
        el.scrollTop += el.scrollHeight - prevScrollHeightRef.current
      }
      prevScrollHeightRef.current = null
    }
    wasFetchingNextPageRef.current = messagesQuery.isFetchingNextPage
  })

  function handleScroll() {
    const el = listRef.current
    if (!el) return
    isAtBottomRef.current =
      el.scrollHeight - el.scrollTop - el.clientHeight < SCROLL_BOTTOM_THRESHOLD_PX
    if (
      el.scrollTop < SCROLL_TOP_THRESHOLD_PX &&
      messagesQuery.hasNextPage &&
      !messagesQuery.isFetchingNextPage
    ) {
      prevScrollHeightRef.current = el.scrollHeight
      messagesQuery.fetchNextPage()
    }
  }

  function scrollToBottom() {
    bottomRef.current?.scrollIntoView()
    isAtBottomRef.current = true
    setHasNewMessages(false)
  }

  function submitMessage() {
    const body = input.trim()
    if (!body || !chatId) return
    const clientMessageId = crypto.randomUUID()
    const visibility: MessageVisibility = staffOnly ? 'staff_only' : 'all'
    updateNewestPage((current) => [
      ...current,
      {
        id: clientMessageId,
        chat_id: chatId,
        sender_id: currentUserId ?? null,
        sender_type: 'user',
        sender_display_name: meQuery.data?.display_name ?? null,
        source_label: null,
        client_message_id: clientMessageId,
        visibility,
        body,
        created_at: new Date().toISOString(),
        pending: true,
      },
    ])
    setInput('')
    sendMutation.mutate({ body, clientMessageId, visibility })
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submitMessage()
    }
  }

  const groups = groupMessages(messages, currentUserId)
  const chats = chatsQuery.data?.pages.flatMap((page) => page.chats) ?? []
  const chat = chats.find((c) => c.id === chatId)
  const title = chat ? chatLabel(chat, currentUserId) : undefined
  const isGroup = (chat?.participant_user_ids.length ?? 0) > 2
  const canComposeStaffOnly = chat?.type === 'client' && getUserKind(token ?? '') === 'staff'

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
      <Box
        ref={listRef}
        data-testid="message-list"
        onScroll={handleScroll}
        sx={{ flex: 1, overflowY: 'auto', pl: 2, pt: 2, ...skyScrollbarSx }}
      >
        {groups.map((group) => {
          const isStaffOnly = group.messages[0].visibility === 'staff_only'
          return (
            <Box
              key={group.messages[0].id}
              sx={{
                mb: 1.5,
                maxWidth: '75%',
                opacity: group.messages[0].pending ? 0.6 : 1,
                bgcolor: isStaffOnly ? STAFF_ONLY_BUBBLE_BG : BUBBLE_BG_BY_SENDER_KIND[group.senderKind],
                border: 1,
                borderColor: isStaffOnly
                  ? STAFF_ONLY_BORDER_COLOR
                  : BUBBLE_BORDER_COLOR_BY_SENDER_KIND[group.senderKind],
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
                  {isStaffOnly && (
                    <Chip label="Interno" size="small" color="secondary" sx={{ height: 18, fontSize: '0.65rem' }} />
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
          )
        })}
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
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
        {canComposeStaffOnly && (
          <FormControlLabel
            sx={{ mx: 0.5, alignSelf: 'flex-start' }}
            control={
              <Checkbox
                size="small"
                checked={staffOnly}
                onChange={(event) => setStaffOnly(event.target.checked)}
              />
            }
            label={<Typography variant="caption">Mensagem interna</Typography>}
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
      </Box>
    </Paper>
  )
}

export default ChatThread
