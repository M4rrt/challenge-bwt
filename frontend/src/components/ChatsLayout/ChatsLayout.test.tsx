import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from '../../lib/auth/AuthContext'
import type { Chat, ChatPage, Message, MessagePage } from '../../lib/api'
import { getMe, listChats, listMessages, markRead } from '../../lib/api'
import ChatsLayout from './ChatsLayout'
import ChatEmptyState from './ChatEmptyState/ChatEmptyState'
import ChatThread from './ChatThread/ChatThread'

vi.mock('../../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../../lib/api')>('../../lib/api')
  return {
    ...actual,
    getMe: vi.fn(),
    listChats: vi.fn(),
    listMessages: vi.fn(),
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

function chatPage(chats: Chat[]): ChatPage {
  return { chats, next_cursor: null }
}

function messagePage(messages: Message[]): MessagePage {
  return { messages, next_cursor: null }
}

beforeEach(() => {
  localStorage.clear()
  localStorage.setItem('chat-app:token', 'token-123')
  FakeWebSocket.instances = []
  vi.stubGlobal('WebSocket', FakeWebSocket)
  vi.mocked(getMe).mockReset().mockResolvedValue({
    id: 'me-id',
    company_id: 'company-1',
    user_kind: 'staff',
    scopes: [],
    display_name: 'ana',
    avatar_url: null,
  })
  vi.mocked(listChats).mockReset().mockResolvedValue(chatPage([]))
  vi.mocked(listMessages).mockReset().mockResolvedValue(messagePage([]))
  vi.mocked(markRead).mockReset().mockResolvedValue({ last_read_at: null, last_read_message_id: null })
})

describe('ChatsLayout', () => {
  it('renders the empty-state placeholder when no chat is selected', async () => {
    const queryClient = new QueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <MemoryRouter initialEntries={['/chats']}>
            <Routes>
              <Route path="/chats" element={<ChatsLayout />}>
                <Route index element={<ChatEmptyState />} />
              </Route>
            </Routes>
          </MemoryRouter>
        </AuthProvider>
      </QueryClientProvider>,
    )

    expect(await screen.findByText('Selecione um chat para começar')).toBeInTheDocument()
  })

  it('renders a "Usar webHook" link pointing to /webhook', async () => {
    const queryClient = new QueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <MemoryRouter initialEntries={['/chats']}>
            <Routes>
              <Route path="/chats" element={<ChatsLayout />}>
                <Route index element={<ChatEmptyState />} />
              </Route>
            </Routes>
          </MemoryRouter>
        </AuthProvider>
      </QueryClientProvider>,
    )

    expect(await screen.findByRole('link', { name: 'Usar webHook' })).toHaveAttribute(
      'href',
      '/webhook',
    )
  })

  it('wires Sidebar and ChatThread together: opening a chat connects both sockets, marks it read, and a live message updates both the thread and (via the user socket) the list', async () => {
    vi.mocked(listChats).mockResolvedValue(
      chatPage([
        makeChat({ id: 'chat-1' }),
        makeChat({ id: 'chat-2', name: 'Carla', participant_user_ids: ['me-id', 'carla-id'] }),
      ]),
    )
    vi.mocked(listMessages).mockImplementation(async (chatId: string) =>
      messagePage(chatId === 'chat-1' ? [makeMessage({})] : []),
    )
    const user = userEvent.setup()

    render(
      <QueryClientProvider client={new QueryClient()}>
        <AuthProvider>
          <MemoryRouter initialEntries={['/chats/chat-1']}>
            <Routes>
              <Route path="/chats" element={<ChatsLayout />}>
                <Route path=":chatId" element={<ChatThread />} />
              </Route>
            </Routes>
          </MemoryRouter>
        </AuthProvider>
      </QueryClientProvider>,
    )

    await screen.findByText('oi ana')
    await screen.findByText('Carla')
    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(2))
    await waitFor(() =>
      expect(markRead).toHaveBeenCalledWith(
        'chat-1',
        expect.objectContaining({ message_id: 'msg-1' }),
        'token-123',
      ),
    )

    const chatSocket = FakeWebSocket.instances.find((instance) =>
      instance.url.includes('/websocket/chats/'),
    )!
    const userSocket = FakeWebSocket.instances.find((instance) =>
      instance.url.includes('/websocket/users/me'),
    )!
    const listChatsCallsBefore = vi.mocked(listChats).mock.calls.length

    chatSocket.onmessage?.({
      data: JSON.stringify(makeMessage({ id: 'msg-2', body: 'chegou ao vivo' })),
    })
    userSocket.onmessage?.({ data: '{}' })

    await screen.findByText('chegou ao vivo')
    await waitFor(() =>
      expect(vi.mocked(listChats).mock.calls.length).toBeGreaterThan(listChatsCallsBefore),
    )

    vi.mocked(markRead).mockClear()
    await user.click(screen.getByText('Carla'))

    // Leaving chat-1 marks *it* as read, up through the message that arrived live while it was
    // open — not chat-2, the one just entered (the mutation's chatId/token travel as variables
    // rather than a closure precisely to keep this call correctly attributed after a navigation).
    await waitFor(() =>
      expect(markRead).toHaveBeenCalledWith(
        'chat-1',
        expect.objectContaining({ message_id: 'msg-2' }),
        'token-123',
      ),
    )
  })
})
