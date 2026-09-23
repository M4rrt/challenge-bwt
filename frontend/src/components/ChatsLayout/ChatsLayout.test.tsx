import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from '../../lib/auth/AuthContext'
import { getMe, listChats, listMessages, listUsers } from '../../lib/api'
import ChatsLayout from './ChatsLayout'
import ChatEmptyState from './ChatEmptyState/ChatEmptyState'
import ChatThread from './ChatThread/ChatThread'

vi.mock('../../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../../lib/api')>('../../lib/api')
  return {
    ...actual,
    getMe: vi.fn(),
    listUsers: vi.fn(),
    listChats: vi.fn(),
    listMessages: vi.fn(),
  }
})

class FakeWebSocket {
  static instances: FakeWebSocket[] = []
  url: string
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }
  close() {}
}

beforeEach(() => {
  localStorage.clear()
  localStorage.setItem('chat-app:token', 'token-123')
  FakeWebSocket.instances = []
  vi.stubGlobal('WebSocket', FakeWebSocket)
  vi.mocked(getMe).mockReset().mockResolvedValue({
    id: 'me-id',
    email: 'ana@example.com',
    username: 'ana',
  })
  vi.mocked(listUsers).mockReset().mockResolvedValue([
    { id: 'me-id', username: 'ana' },
    { id: 'beto-id', username: 'beto' },
    { id: 'carla-id', username: 'carla' },
  ])
  vi.mocked(listChats).mockReset().mockResolvedValue([])
  vi.mocked(listMessages).mockReset().mockResolvedValue([])
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

  it('does not show a stale new-activity indicator on the chat just left, after a live message arrived while it was open', async () => {
    vi.mocked(listChats)
      .mockResolvedValueOnce([
        { id: 'chat-1', name: null, participant_user_ids: ['me-id', 'beto-id'], last_message_at: '2026-08-06T12:00:00Z' },
        { id: 'chat-2', name: null, participant_user_ids: ['me-id', 'carla-id'], last_message_at: null },
      ])
      .mockResolvedValue([
        { id: 'chat-1', name: null, participant_user_ids: ['me-id', 'beto-id'], last_message_at: '2026-08-06T12:05:00Z' },
        { id: 'chat-2', name: null, participant_user_ids: ['me-id', 'carla-id'], last_message_at: null },
      ])
    vi.mocked(listMessages).mockImplementation(async (chatId: string) =>
      chatId === 'chat-1'
        ? [
            {
              id: 'msg-1',
              chat_id: 'chat-1',
              sender_id: 'beto-id',
              sender_type: 'user',
              source_label: null,
              body: 'oi ana',
              created_at: '2026-08-06T12:00:00Z',
            },
          ]
        : [],
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
    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(2))

    const chatSocket = FakeWebSocket.instances.find((instance) =>
      instance.url.includes('/websocket/chats/'),
    )!
    const userSocket = FakeWebSocket.instances.find((instance) =>
      instance.url.includes('/websocket/users/me'),
    )!

    // A new message arrives in chat-1 while it's still open: the chat
    // socket delivers it to ChatThread, and the user socket tells Sidebar to
    // refetch, picking up the newer last_message_at from the mock above.
    chatSocket.onmessage?.({
      data: JSON.stringify({
        id: 'msg-2',
        chat_id: 'chat-1',
        sender_id: 'beto-id',
        sender_type: 'user',
        source_label: null,
        body: 'chegou ao vivo',
        created_at: '2026-08-06T12:05:00Z',
      }),
    })
    userSocket.onmessage?.({ data: '{}' })

    await waitFor(() => expect(listChats).toHaveBeenCalledTimes(2))
    await screen.findByText('chegou ao vivo')

    await user.click(screen.getByText('carla'))

    expect(screen.queryByLabelText('Nova atividade')).not.toBeInTheDocument()
  })
})
