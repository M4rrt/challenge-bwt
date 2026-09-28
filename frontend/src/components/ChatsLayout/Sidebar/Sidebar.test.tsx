import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from '../../../lib/auth/AuthContext'
import type { Chat, ChatPage } from '../../../lib/api'
import { getMe, listChats } from '../../../lib/api'
import Sidebar from './Sidebar'

vi.mock('../../../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../../../lib/api')>('../../../lib/api')
  return {
    ...actual,
    getMe: vi.fn(),
    listChats: vi.fn(),
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

const ME = {
  id: 'me-id',
  company_id: 'company-1',
  user_kind: 'staff' as const,
  scopes: [],
  display_name: 'ana',
  avatar_url: null,
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

function page(chats: Chat[], next_cursor: string | null = null): ChatPage {
  return { chats, next_cursor }
}

function renderChats() {
  const queryClient = new QueryClient()
  localStorage.setItem('chat-app:token', 'token-123')
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter initialEntries={['/chats']}>
          <Routes>
            <Route path="/chats" element={<Sidebar />} />
            <Route path="/chats/:chatId" element={<Sidebar />} />
            <Route path="/" element={<div>Login page</div>} />
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

  vi.mocked(getMe).mockReset()
  vi.mocked(listChats).mockReset()

  vi.mocked(getMe).mockResolvedValue(ME)
})

describe('Sidebar', () => {
  it('shows the chat count in the list header', async () => {
    vi.mocked(listChats).mockResolvedValue(
      page([
        makeChat({ id: 'chat-1', name: 'Trio', participant_user_ids: ['me-id', 'beto-id', 'carla-id'] }),
        makeChat({ id: 'chat-2', name: null }),
      ]),
    )
    renderChats()

    expect(await screen.findByRole('heading', { name: 'Chats (2)' })).toBeInTheDocument()
  })

  it("renders each chat, resolving an unnamed 1:1 to the other participant's name off their last message", async () => {
    vi.mocked(listChats).mockResolvedValue(
      page([
        makeChat({
          id: 'chat-1',
          last_message: {
            id: 'msg-1',
            chat_id: 'chat-1',
            sender_id: 'beto-id',
            sender_type: 'user',
            sender_display_name: 'beto',
            source_label: null,
            body: 'oi',
            created_at: '2026-08-06T12:00:00Z',
          },
        }),
        makeChat({ id: 'chat-2', name: 'Trio', participant_user_ids: ['me-id', 'beto-id', 'carla-id'] }),
      ]),
    )
    renderChats()

    expect(await screen.findByText('beto')).toBeInTheDocument()
    expect(await screen.findByText('Trio')).toBeInTheDocument()
  })

  it('shows a person icon for a 1:1 item and a group icon for a group item', async () => {
    vi.mocked(listChats).mockResolvedValue(
      page([
        makeChat({ id: 'chat-1' }),
        makeChat({ id: 'chat-2', name: 'Trio', participant_user_ids: ['me-id', 'beto-id', 'carla-id'] }),
      ]),
    )
    renderChats()

    await screen.findByText('Trio')
    expect(screen.getByLabelText('Chat individual')).toBeInTheDocument()
    expect(screen.getByLabelText('Chat em grupo')).toBeInTheDocument()
  })

  it("shows the last message body as a preview", async () => {
    vi.mocked(listChats).mockResolvedValue(
      page([
        makeChat({
          id: 'chat-1',
          name: 'Trio',
          last_message: {
            id: 'msg-1',
            chat_id: 'chat-1',
            sender_id: 'beto-id',
            sender_type: 'user',
            sender_display_name: 'beto',
            source_label: null,
            body: 'oi pessoal',
            created_at: '2026-08-06T12:00:00Z',
          },
        }),
      ]),
    )
    renderChats()

    expect(await screen.findByText('oi pessoal')).toBeInTheDocument()
  })

  it('shows a placeholder preview when the chat has no messages yet', async () => {
    vi.mocked(listChats).mockResolvedValue(page([makeChat({ id: 'chat-1', name: 'Trio' })]))
    renderChats()

    expect(await screen.findByText('Nenhuma mensagem ainda')).toBeInTheDocument()
  })

  it('shows an unread-count badge for a chat with unread messages', async () => {
    vi.mocked(listChats).mockResolvedValue(
      page([makeChat({ id: 'chat-1', name: 'Trio', unread_count: 3 })]),
    )
    renderChats()

    expect(await screen.findByText('3')).toBeInTheDocument()
  })

  it('does not show an unread-count badge when there is nothing unread', async () => {
    vi.mocked(listChats).mockResolvedValue(
      page([makeChat({ id: 'chat-1', name: 'Trio', unread_count: 0 })]),
    )
    renderChats()

    await screen.findByText('Trio')
    expect(screen.queryByText('0')).not.toBeInTheDocument()
  })

  it('does not show an unread-count badge for the chat currently open', async () => {
    vi.mocked(listChats).mockResolvedValue(
      page([makeChat({ id: 'chat-1', name: 'Trio', unread_count: 3 })]),
    )
    localStorage.setItem('chat-app:token', 'token-123')
    render(
      <QueryClientProvider client={new QueryClient()}>
        <AuthProvider>
          <MemoryRouter initialEntries={['/chats/chat-1']}>
            <Routes>
              <Route path="/chats/:chatId" element={<Sidebar />} />
            </Routes>
          </MemoryRouter>
        </AuthProvider>
      </QueryClientProvider>,
    )

    await screen.findByText('Trio')
    expect(screen.queryByText('3')).not.toBeInTheDocument()
  })

  it('sends the typed search text to listChats, debounced', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.mocked(listChats).mockResolvedValue(page([]))
    const user = userEvent.setup({ delay: null })
    localStorage.setItem('chat-app:token', 'token-123')
    render(
      <QueryClientProvider client={new QueryClient()}>
        <AuthProvider>
          <MemoryRouter initialEntries={['/chats']}>
            <Routes>
              <Route path="/chats" element={<Sidebar />} />
            </Routes>
          </MemoryRouter>
        </AuthProvider>
      </QueryClientProvider>,
    )

    await user.type(await screen.findByPlaceholderText('Buscar por nome'), 'bet')
    await vi.advanceTimersByTimeAsync(500)

    await waitFor(() =>
      expect(listChats).toHaveBeenCalledWith('token-123', expect.objectContaining({ search: 'bet' })),
    )
    vi.useRealTimers()
  })

  it('fetches the next page when the list is scrolled near its bottom', async () => {
    vi.mocked(listChats)
      .mockResolvedValueOnce(page([makeChat({ id: 'chat-1', name: 'Um' })], 'cursor-1'))
      .mockResolvedValueOnce(page([makeChat({ id: 'chat-2', name: 'Dois' })], null))
    renderChats()

    const list = await screen.findByRole('list')
    await screen.findByText('Um')

    Object.defineProperty(list, 'scrollHeight', { value: 1000, configurable: true })
    Object.defineProperty(list, 'clientHeight', { value: 300, configurable: true })
    Object.defineProperty(list, 'scrollTop', { value: 690, configurable: true })
    list.dispatchEvent(new Event('scroll', { bubbles: false }))

    await screen.findByText('Dois')
    expect(listChats).toHaveBeenCalledWith('token-123', expect.objectContaining({ before: 'cursor-1' }))
  })

  it('refetches the chat list when the user-channel socket receives a message', async () => {
    vi.mocked(listChats).mockResolvedValue(page([]))
    renderChats()

    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1))
    expect(FakeWebSocket.instances[0].url).toContain('/websocket/users/me?token=token-123')
    expect(listChats).toHaveBeenCalledTimes(1)

    FakeWebSocket.instances[0].onmessage?.({ data: '{}' })

    await waitFor(() => expect(listChats).toHaveBeenCalledTimes(2))
  })

  it('logs out and returns to the login page when the user socket reports UNAUTHENTICATED', async () => {
    vi.mocked(listChats).mockResolvedValue(page([]))
    renderChats()

    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1))
    FakeWebSocket.instances[0].onclose?.({ code: 1008 })

    expect(await screen.findByText('Login page')).toBeInTheDocument()
  })
})
