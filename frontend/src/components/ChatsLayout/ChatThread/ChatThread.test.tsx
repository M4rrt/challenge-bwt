import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from '../../../lib/auth/AuthContext'
import type { Chat, ChatPage, CurrentUser, Message, MessagePage } from '../../../lib/api'
import { getMe, listChats, listMessages, markRead, sendMessage } from '../../../lib/api'
import ChatThread from './ChatThread'

vi.mock('../../../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../../../lib/api')>('../../../lib/api')
  return {
    ...actual,
    getMe: vi.fn(),
    listChats: vi.fn(),
    listMessages: vi.fn(),
    sendMessage: vi.fn(),
    markRead: vi.fn(),
  }
})

class FakeWebSocket {
  static instances: FakeWebSocket[] = []
  url: string
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: ((event: { code: number }) => void) | null = null
  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }
  close() {}
}

function makeJwt(payload: Record<string, unknown>): string {
  const encode = (value: unknown) =>
    btoa(JSON.stringify(value)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  return `${encode({ alg: 'HS256', typ: 'JWT' })}.${encode(payload)}.fake-signature`
}

const STAFF_TOKEN = makeJwt({
  sub: 'me-id',
  'https://brwinetours.com/chat': { user_kind: 'staff' },
})
const CLIENT_TOKEN = makeJwt({
  sub: 'me-id',
  'https://brwinetours.com/chat': { user_kind: 'client' },
})

const ME: CurrentUser = {
  id: 'me-id',
  company_id: 'company-1',
  user_kind: 'staff',
  scopes: [],
  display_name: 'ana',
  avatar_url: null,
}

function makeMessage(overrides: Partial<Message>): Message {
  return {
    id: 'msg-1',
    chat_id: 'chat-1',
    sender_id: 'beto-id',
    sender_type: 'user',
    sender_display_name: 'beto',
    source_label: null,
    body: 'oi ana',
    created_at: '2026-08-06T12:00:00Z',
    ...overrides,
  }
}

function makeChat(overrides: Partial<Chat>): Chat {
  return {
    id: 'chat-1',
    type: 'staff',
    name: null,
    participant_user_ids: ['me-id', 'beto-id'],
    last_message: null,
    last_message_at: null,
    unread_count: 0,
    last_read_at: null,
    last_read_message_id: null,
    ...overrides,
  }
}

function chatPage(chats: Chat[]): ChatPage {
  return { chats, next_cursor: null }
}

function messagePage(messages: Message[], next_cursor: string | null = null): MessagePage {
  return { messages, next_cursor }
}

function renderChatThread(token = 'token-123') {
  const queryClient = new QueryClient()
  localStorage.setItem('chat-app:token', token)
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter initialEntries={['/chats/chat-1']}>
          <Routes>
            <Route path="/chats" element={<div>Chats view</div>} />
            <Route path="/chats/:chatId" element={<ChatThread />} />
            <Route path="/" element={<div>Login page</div>} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  )
}

function renderChatThreadWithNavigation() {
  const queryClient = new QueryClient()
  localStorage.setItem('chat-app:token', 'token-123')
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter initialEntries={['/chats/chat-1']}>
          <Link to="/chats/chat-2">ir para chat-2</Link>
          <Routes>
            <Route path="/chats/:chatId" element={<ChatThread />} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  localStorage.clear()
  FakeWebSocket.instances = []
  vi.stubGlobal('WebSocket', FakeWebSocket)

  vi.mocked(getMe).mockReset().mockResolvedValue(ME)
  vi.mocked(listChats).mockReset().mockResolvedValue(chatPage([makeChat({})]))
  vi.mocked(listMessages).mockReset()
  vi.mocked(sendMessage).mockReset()
  vi.mocked(markRead).mockReset().mockResolvedValue({ last_read_at: null, last_read_message_id: null })
})

describe('Chat', () => {
  it("shows the other participant's name at the top for an unnamed 1:1 chat, off their last message", async () => {
    vi.mocked(listChats).mockResolvedValue(
      chatPage([
        makeChat({
          last_message: makeMessage({ sender_id: 'beto-id', sender_display_name: 'beto' }),
        }),
      ]),
    )
    vi.mocked(listMessages).mockResolvedValue(messagePage([]))
    renderChatThread()

    expect(await screen.findByRole('heading', { name: 'beto' })).toBeInTheDocument()
  })

  it('shows an individual-chat icon in the header for a 1:1 chat', async () => {
    vi.mocked(listMessages).mockResolvedValue(messagePage([]))
    renderChatThread()

    expect(await screen.findByLabelText('Chat individual')).toBeInTheDocument()
  })

  it('shows the chat name at the top for a named/group chat', async () => {
    vi.mocked(listChats).mockResolvedValue(
      chatPage([makeChat({ name: 'Trio', participant_user_ids: ['me-id', 'beto-id', 'carla-id'] })]),
    )
    vi.mocked(listMessages).mockResolvedValue(messagePage([]))
    renderChatThread()

    expect(await screen.findByRole('heading', { name: 'Trio' })).toBeInTheDocument()
  })

  it('shows a group-chat icon in the header for a group chat, not the individual one', async () => {
    vi.mocked(listChats).mockResolvedValue(
      chatPage([makeChat({ name: 'Trio', participant_user_ids: ['me-id', 'beto-id', 'carla-id'] })]),
    )
    vi.mocked(listMessages).mockResolvedValue(messagePage([]))
    renderChatThread()

    expect(await screen.findByLabelText('Chat em grupo')).toBeInTheDocument()
    expect(screen.queryByLabelText('Chat individual')).not.toBeInTheDocument()
  })

  it('renders the message backlog on open', async () => {
    vi.mocked(listMessages).mockResolvedValue(messagePage([makeMessage({})]))
    renderChatThread()

    expect(await screen.findByText('oi ana')).toBeInTheDocument()
  })

  it('shows a message pushed over the websocket without refetching the backlog', async () => {
    vi.mocked(listMessages).mockResolvedValue(messagePage([]))
    renderChatThread()

    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1))
    expect(listMessages).toHaveBeenCalledTimes(1)

    const socket = FakeWebSocket.instances[0]
    socket.onmessage?.({
      data: JSON.stringify(makeMessage({ id: 'msg-2', body: 'chegou ao vivo' })),
    })

    expect(await screen.findByText('chegou ao vivo')).toBeInTheDocument()
    expect(listMessages).toHaveBeenCalledTimes(1)
  })

  it('shows a sent message immediately, and reconciles it once the server confirms it', async () => {
    vi.mocked(listMessages).mockResolvedValue(messagePage([]))
    let resolveSend: (value: Message) => void = () => {}
    vi.mocked(sendMessage).mockReturnValue(
      new Promise((resolve) => {
        resolveSend = resolve
      }),
    )
    const user = userEvent.setup()
    renderChatThread()

    const input = await screen.findByRole('textbox')
    await user.type(input, 'oi beto{Enter}')

    expect(await screen.findByText('oi beto')).toBeInTheDocument()
    expect(sendMessage).toHaveBeenCalledWith('chat-1', 'oi beto', expect.any(String), 'token-123', 'all')

    resolveSend(
      makeMessage({ id: 'msg-3', sender_id: 'me-id', sender_display_name: 'ana', body: 'oi beto' }),
    )

    await waitFor(() => expect(screen.getAllByText('oi beto')).toHaveLength(1))
  })

  it("marks the optimistic bubble as the sender's own even before getMe has resolved, using the id encoded in the token", async () => {
    vi.mocked(listMessages).mockResolvedValue(messagePage([]))
    vi.mocked(getMe).mockReturnValue(new Promise(() => {})) // never resolves
    vi.mocked(sendMessage).mockReturnValue(new Promise(() => {})) // never resolves
    const user = userEvent.setup()
    renderChatThread(STAFF_TOKEN) // STAFF_TOKEN's sub claim is 'me-id'

    const input = await screen.findByRole('textbox')
    await user.type(input, 'oi beto{Enter}')

    expect(await screen.findByText('oi beto')).toHaveAttribute('data-sender-kind', 'me')
  })

  it('does not duplicate a message the live socket echoes back before the REST response resolves', async () => {
    vi.mocked(listMessages).mockResolvedValue(messagePage([]))
    let resolveSend: (value: Message) => void = () => {}
    vi.mocked(sendMessage).mockReturnValue(
      new Promise((resolve) => {
        resolveSend = resolve
      }),
    )
    const user = userEvent.setup()
    renderChatThread()
    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1))

    const input = await screen.findByRole('textbox')
    await user.type(input, 'oi beto{Enter}')
    await screen.findByText('oi beto')

    const [, , clientMessageId] = vi.mocked(sendMessage).mock.calls[0]
    const confirmed = makeMessage({
      id: 'msg-3',
      sender_id: 'me-id',
      sender_display_name: 'ana',
      body: 'oi beto',
      client_message_id: clientMessageId as string,
    })
    FakeWebSocket.instances[0].onmessage?.({ data: JSON.stringify(confirmed) })

    expect(screen.getAllByText('oi beto')).toHaveLength(1)

    resolveSend(confirmed)
    await waitFor(() => expect(screen.getAllByText('oi beto')).toHaveLength(1))
  })

  it('removes the optimistic bubble and restores the typed text when sending fails', async () => {
    vi.mocked(listMessages).mockResolvedValue(messagePage([]))
    let rejectSend: (error: Error) => void = () => {}
    vi.mocked(sendMessage).mockReturnValue(
      new Promise((_resolve, reject) => {
        rejectSend = reject
      }),
    )
    const user = userEvent.setup()
    renderChatThread()

    const input = (await screen.findByRole('textbox')) as HTMLTextAreaElement
    await user.type(input, 'oi beto{Enter}')

    const messageList = await screen.findByTestId('message-list')
    await within(messageList).findByText('oi beto')

    rejectSend(new Error('network error'))

    await waitFor(() => expect(within(messageList).queryByText('oi beto')).not.toBeInTheDocument())
    expect(input.value).toBe('oi beto')
  })

  it('does not clobber a newer draft with the failed text when a send fails after the user has already started a follow-up message', async () => {
    vi.mocked(listMessages).mockResolvedValue(messagePage([]))
    let rejectSend: (error: Error) => void = () => {}
    vi.mocked(sendMessage).mockReturnValue(
      new Promise((_resolve, reject) => {
        rejectSend = reject
      }),
    )
    const user = userEvent.setup()
    renderChatThread()

    const input = (await screen.findByRole('textbox')) as HTMLTextAreaElement
    await user.type(input, 'oi beto{Enter}')
    await screen.findByText('oi beto')

    await user.type(input, 'novo texto')
    rejectSend(new Error('network error'))

    await waitFor(() => expect(screen.queryByText('oi beto')).not.toBeInTheDocument())
    expect(input.value).toBe('novo texto')
  })

  it('marks message bubbles with the sender kind (me, other, external)', async () => {
    vi.mocked(listMessages).mockResolvedValue(
      messagePage([
        makeMessage({ id: 'msg-1', sender_id: 'me-id', sender_display_name: 'ana', body: 'minha mensagem' }),
        makeMessage({ id: 'msg-2', sender_id: 'beto-id', sender_display_name: 'beto', body: 'mensagem do beto' }),
        makeMessage({
          id: 'msg-3',
          sender_id: null,
          sender_type: 'external',
          sender_display_name: null,
          source_label: 'Zapier',
          body: 'mensagem do webhook',
        }),
      ]),
    )
    renderChatThread()

    expect(await screen.findByText('minha mensagem')).toHaveAttribute('data-sender-kind', 'me')
    expect(screen.getByText('mensagem do beto')).toHaveAttribute('data-sender-kind', 'other')
    expect(screen.getByText('mensagem do webhook')).toHaveAttribute('data-sender-kind', 'external')
  })

  it('shows an info tooltip on external/webhook messages explaining the source, but not on others', async () => {
    vi.mocked(listMessages).mockResolvedValue(
      messagePage([
        makeMessage({ id: 'msg-1', sender_id: 'me-id', sender_display_name: 'ana', body: 'minha mensagem' }),
        makeMessage({
          id: 'msg-2',
          sender_id: null,
          sender_type: 'external',
          sender_display_name: null,
          source_label: 'Zapier',
          body: 'mensagem do webhook',
        }),
      ]),
    )
    renderChatThread()

    await screen.findByText('minha mensagem')
    expect(screen.getByLabelText('Essa mensagem veio de um serviço externo')).toBeInTheDocument()
    expect(screen.getAllByLabelText('Essa mensagem veio de um serviço externo')).toHaveLength(1)
  })

  it('marks a Staff-only message with an "Interno" tag', async () => {
    vi.mocked(listMessages).mockResolvedValue(
      messagePage([makeMessage({ body: 'nota interna', visibility: 'staff_only' })]),
    )
    renderChatThread()

    await screen.findByText('nota interna')
    expect(screen.getByText('Interno')).toBeInTheDocument()
  })

  it('does not tag an ordinary message as internal', async () => {
    vi.mocked(listMessages).mockResolvedValue(messagePage([makeMessage({ visibility: 'all' })]))
    renderChatThread()

    await screen.findByText('oi ana')
    expect(screen.queryByText('Interno')).not.toBeInTheDocument()
  })

  it('loads an older page when scrolled near the top, without duplicating or reordering', async () => {
    vi.mocked(listMessages)
      .mockResolvedValueOnce(
        messagePage([makeMessage({ id: 'msg-2', body: 'mensagem nova', created_at: '2026-08-06T12:05:00Z' })], 'cursor-1'),
      )
      .mockResolvedValueOnce(
        messagePage([makeMessage({ id: 'msg-1', body: 'mensagem antiga', created_at: '2026-08-06T12:00:00Z' })], null),
      )
    renderChatThread()

    const list = await screen.findByTestId('message-list')
    await screen.findByText('mensagem nova')

    Object.defineProperty(list, 'scrollTop', { value: 0, writable: true, configurable: true })
    Object.defineProperty(list, 'scrollHeight', { value: 500, configurable: true })
    list.dispatchEvent(new Event('scroll', { bubbles: false }))

    await screen.findByText('mensagem antiga')
    expect(listMessages).toHaveBeenCalledWith('chat-1', 'token-123', { before: 'cursor-1' })

    const bodies = screen.getAllByText(/mensagem (nova|antiga)/).map((el) => el.textContent)
    expect(bodies).toEqual(['mensagem antiga', 'mensagem nova'])
  })

  it('marks the chat as read on open and again on close, up to the newest loaded message', async () => {
    vi.mocked(listMessages).mockResolvedValue(messagePage([makeMessage({ id: 'msg-1' })]))
    const { unmount } = renderChatThread()

    await screen.findByText('oi ana')
    await waitFor(() =>
      expect(markRead).toHaveBeenCalledWith(
        'chat-1',
        expect.objectContaining({ message_id: 'msg-1' }),
        'token-123',
      ),
    )

    unmount()
    await waitFor(() => expect(markRead).toHaveBeenCalledTimes(2))
  })

  it('marks the chat as read for the chat left when switching to another one', async () => {
    vi.mocked(listMessages).mockImplementation(async (chatId: string) =>
      messagePage(chatId === 'chat-1' ? [makeMessage({ id: 'msg-1' })] : []),
    )
    const user = userEvent.setup()
    renderChatThreadWithNavigation()

    await screen.findByText('oi ana')
    await waitFor(() => expect(markRead).toHaveBeenCalledTimes(1))
    vi.mocked(markRead).mockClear()

    await user.click(screen.getByText('ir para chat-2'))

    // The chat left, not the one just entered — this is the one thing an offset-free assertion
    // here has to prove: chatId/token travel through the mutation's own variables rather than
    // a closure, precisely because this call fires from an unmount cleanup that TanStack Query's
    // per-render rebinding would otherwise attribute to chat-2 by the time it runs.
    await waitFor(() =>
      expect(markRead).toHaveBeenCalledWith(
        'chat-1',
        expect.objectContaining({ message_id: 'msg-1' }),
        'token-123',
      ),
    )
  })

  describe('Staff-only compose', () => {
    it('shows the "Mensagem interna" checkbox for a staff member in a Client Chat', async () => {
      vi.mocked(listChats).mockResolvedValue(chatPage([makeChat({ type: 'client' })]))
      vi.mocked(listMessages).mockResolvedValue(messagePage([]))
      renderChatThread(STAFF_TOKEN)

      expect(await screen.findByRole('checkbox', { name: 'Mensagem interna' })).toBeInTheDocument()
    })

    it('does not show the checkbox in a Staff Chat', async () => {
      vi.mocked(listChats).mockResolvedValue(chatPage([makeChat({ type: 'staff' })]))
      vi.mocked(listMessages).mockResolvedValue(messagePage([]))
      renderChatThread(STAFF_TOKEN)

      await screen.findByRole('textbox')
      expect(screen.queryByRole('checkbox', { name: 'Mensagem interna' })).not.toBeInTheDocument()
    })

    it('does not show the checkbox for an end client', async () => {
      vi.mocked(listChats).mockResolvedValue(chatPage([makeChat({ type: 'client' })]))
      vi.mocked(listMessages).mockResolvedValue(messagePage([]))
      renderChatThread(CLIENT_TOKEN)

      await screen.findByRole('textbox')
      expect(screen.queryByRole('checkbox', { name: 'Mensagem interna' })).not.toBeInTheDocument()
    })

    it('sends visibility staff_only when the checkbox is checked', async () => {
      vi.mocked(listChats).mockResolvedValue(chatPage([makeChat({ type: 'client' })]))
      vi.mocked(listMessages).mockResolvedValue(messagePage([]))
      vi.mocked(sendMessage).mockResolvedValue(makeMessage({ visibility: 'staff_only' }))
      const user = userEvent.setup()
      renderChatThread(STAFF_TOKEN)

      await user.click(await screen.findByRole('checkbox', { name: 'Mensagem interna' }))
      await user.type(await screen.findByRole('textbox'), 'nota interna{Enter}')

      expect(sendMessage).toHaveBeenCalledWith(
        'chat-1',
        'nota interna',
        expect.any(String),
        STAFF_TOKEN,
        'staff_only',
      )
    })
  })

  describe('WebSocket close codes', () => {
    it('leaves the chat and returns to the chat list when access is revoked', async () => {
      vi.mocked(listMessages).mockResolvedValue(messagePage([]))
      renderChatThread()

      await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1))
      FakeWebSocket.instances[0].onclose?.({ code: 4403 })

      expect(await screen.findByText('Chats view')).toBeInTheDocument()
    })

    it('logs out and returns to the login page when the credential was never valid', async () => {
      vi.mocked(listMessages).mockResolvedValue(messagePage([]))
      renderChatThread()

      await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1))
      FakeWebSocket.instances[0].onclose?.({ code: 1008 })

      expect(await screen.findByText('Login page')).toBeInTheDocument()
    })
  })
})
