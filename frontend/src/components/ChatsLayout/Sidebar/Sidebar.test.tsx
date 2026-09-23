import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from '../../../lib/auth/AuthContext'
import { createChat, getMe, listChats, listUsers } from '../../../lib/api'
import Sidebar from './Sidebar'

vi.mock('../../../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../../../lib/api')>('../../../lib/api')
  return {
    ...actual,
    getMe: vi.fn(),
    listUsers: vi.fn(),
    listChats: vi.fn(),
    createChat: vi.fn(),
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

const ME = { id: 'me-id', email: 'ana@example.com', username: 'ana' }
const USERS = [
  { id: 'me-id', username: 'ana' },
  { id: 'beto-id', username: 'beto' },
  { id: 'carla-id', username: 'carla' },
]

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
  vi.mocked(listUsers).mockReset()
  vi.mocked(listChats).mockReset()
  vi.mocked(createChat).mockReset()

  vi.mocked(getMe).mockResolvedValue(ME)
  vi.mocked(listUsers).mockResolvedValue(USERS)
})

describe('Sidebar', () => {
  it('shows the chat count in the list header', async () => {
    vi.mocked(listChats).mockResolvedValue([
      { id: 'chat-1', name: null, participant_user_ids: ['me-id', 'beto-id'], last_message_at: null },
      {
        id: 'chat-2',
        name: 'Trio',
        participant_user_ids: ['me-id', 'beto-id', 'carla-id'],
        last_message_at: null,
      },
    ])
    renderChats()

    expect(await screen.findByRole('heading', { name: 'Chats (2)' })).toBeInTheDocument()
  })

  it("renders the user's chats, resolving 1:1s to the other participant's username", async () => {
    vi.mocked(listChats).mockResolvedValue([
      { id: 'chat-1', name: null, participant_user_ids: ['me-id', 'beto-id'], last_message_at: null },
      {
        id: 'chat-2',
        name: 'Trio',
        participant_user_ids: ['me-id', 'beto-id', 'carla-id'],
        last_message_at: null,
      },
    ])
    renderChats()

    expect(await screen.findByText('beto')).toBeInTheDocument()
    expect(await screen.findByText('Trio')).toBeInTheDocument()
  })

  it('shows a person icon for a 1:1 item and a group icon for a group item', async () => {
    vi.mocked(listChats).mockResolvedValue([
      { id: 'chat-1', name: null, participant_user_ids: ['me-id', 'beto-id'], last_message_at: null },
      {
        id: 'chat-2',
        name: 'Trio',
        participant_user_ids: ['me-id', 'beto-id', 'carla-id'],
        last_message_at: null,
      },
    ])
    renderChats()

    await screen.findByText('beto')
    expect(screen.getByLabelText('Chat individual')).toBeInTheDocument()
    expect(screen.getByLabelText('Chat em grupo')).toBeInTheDocument()
  })

  it('renders the "Nova chat" button before the chat list', async () => {
    vi.mocked(listChats).mockResolvedValue([
      { id: 'chat-1', name: null, participant_user_ids: ['me-id', 'beto-id'], last_message_at: null },
    ])
    renderChats()

    const button = await screen.findByRole('button', { name: 'Nova chat' })
    const item = await screen.findByText('beto')

    expect(button.compareDocumentPosition(item) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('refetches the user list when opening the new-chat form', async () => {
    vi.mocked(listChats).mockResolvedValue([])
    const user = userEvent.setup()
    renderChats()

    await waitFor(() => expect(listUsers).toHaveBeenCalledTimes(1))

    await user.click(await screen.findByRole('button', { name: 'Nova chat' }))

    await waitFor(() => expect(listUsers).toHaveBeenCalledTimes(2))
  })

  it('requires a name before creating a group chat', async () => {
    vi.mocked(listChats).mockResolvedValue([])
    const user = userEvent.setup()
    renderChats()

    await user.click(await screen.findByRole('button', { name: 'Nova chat' }))
    await user.click(screen.getByRole('checkbox', { name: 'beto' }))
    await user.click(screen.getByRole('checkbox', { name: 'carla' }))

    expect(screen.getByPlaceholderText(/Nome do Grupo/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Criar' }))

    expect(createChat).not.toHaveBeenCalled()

    await user.type(screen.getByPlaceholderText(/Nome do Grupo/i), 'Trio')
    await user.click(screen.getByRole('button', { name: 'Criar' }))

    await waitFor(() =>
      expect(createChat).toHaveBeenCalledWith(
        ['beto-id', 'carla-id'],
        'Trio',
        'token-123',
      ),
    )
  })

  it('does not duplicate an existing 1:1 chat when the same contact is picked again', async () => {
    // listChats always resolves to this same single-item array, so this would
    // fail if the create mutation appended its response into the list locally instead
    // of relying on the (idempotent) backend + a refetch.
    const existingChat = {
      id: 'chat-1',
      name: null,
      participant_user_ids: ['me-id', 'beto-id'],
      last_message_at: null,
    }
    vi.mocked(listChats).mockResolvedValue([existingChat])
    vi.mocked(createChat).mockResolvedValue(existingChat)
    const user = userEvent.setup()
    renderChats()

    expect(await screen.findByText('beto')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Nova chat' }))
    await user.click(screen.getByRole('checkbox', { name: 'beto' }))
    await user.click(screen.getByRole('button', { name: 'Criar' }))

    await waitFor(() => expect(createChat).toHaveBeenCalledWith(['beto-id'], undefined, 'token-123'))
    expect(await screen.findAllByText('beto')).toHaveLength(1)
  })

  it('refetches the chat list when the user-channel socket receives a message', async () => {
    vi.mocked(listChats).mockResolvedValue([])
    renderChats()

    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1))
    expect(FakeWebSocket.instances[0].url).toContain('/websocket/users/me?token=token-123')
    expect(listChats).toHaveBeenCalledTimes(1)

    FakeWebSocket.instances[0].onmessage?.({ data: '{}' })

    await waitFor(() => expect(listChats).toHaveBeenCalledTimes(2))
  })

  it('shows a new-activity indicator for a chat with a message newer than the last-seen cursor', async () => {
    localStorage.setItem('chat-app:lastSeen:me-id:chat-1', '2026-08-06T12:00:00Z')
    vi.mocked(listChats).mockResolvedValue([
      {
        id: 'chat-1',
        name: null,
        participant_user_ids: ['me-id', 'beto-id'],
        last_message_at: '2026-08-06T12:05:00Z',
      },
    ])
    renderChats()

    expect(await screen.findByLabelText('Nova atividade')).toBeInTheDocument()
  })

  it('does not show a new-activity indicator when the last-seen cursor is already current', async () => {
    localStorage.setItem('chat-app:lastSeen:me-id:chat-1', '2026-08-06T12:05:00Z')
    vi.mocked(listChats).mockResolvedValue([
      {
        id: 'chat-1',
        name: null,
        participant_user_ids: ['me-id', 'beto-id'],
        last_message_at: '2026-08-06T12:05:00Z',
      },
    ])
    renderChats()

    await screen.findByText('beto')
    expect(screen.queryByLabelText('Nova atividade')).not.toBeInTheDocument()
  })

  it('does not show a new-activity indicator when there is no stored cursor (cold start)', async () => {
    vi.mocked(listChats).mockResolvedValue([
      {
        id: 'chat-1',
        name: null,
        participant_user_ids: ['me-id', 'beto-id'],
        last_message_at: '2026-08-06T12:05:00Z',
      },
    ])
    renderChats()

    await screen.findByText('beto')
    expect(screen.queryByLabelText('Nova atividade')).not.toBeInTheDocument()
  })

  it('does not show a new-activity indicator for the chat currently open', async () => {
    localStorage.setItem('chat-app:lastSeen:me-id:chat-1', '2026-08-06T12:00:00Z')
    vi.mocked(listChats).mockResolvedValue([
      {
        id: 'chat-1',
        name: null,
        participant_user_ids: ['me-id', 'beto-id'],
        last_message_at: '2026-08-06T12:05:00Z',
      },
    ])
    const queryClient = new QueryClient()
    localStorage.setItem('chat-app:token', 'token-123')
    render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <MemoryRouter initialEntries={['/chats/chat-1']}>
            <Routes>
              <Route path="/chats/:chatId" element={<Sidebar />} />
            </Routes>
          </MemoryRouter>
        </AuthProvider>
      </QueryClientProvider>,
    )

    await screen.findByText('beto')
    expect(screen.queryByLabelText('Nova atividade')).not.toBeInTheDocument()
  })

  it('navigates to the new chat after creating it', async () => {
    vi.mocked(listChats).mockResolvedValue([])
    const newChat = {
      id: 'chat-new',
      name: null,
      participant_user_ids: ['me-id', 'beto-id'],
      last_message_at: null,
    }
    vi.mocked(createChat).mockResolvedValue(newChat)
    const user = userEvent.setup()
    const queryClient = new QueryClient()
    localStorage.setItem('chat-app:token', 'token-123')
    render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <MemoryRouter initialEntries={['/chats']}>
            <Routes>
              <Route path="/chats" element={<Sidebar />} />
              <Route path="/chats/:chatId" element={<div>Chat view</div>} />
            </Routes>
          </MemoryRouter>
        </AuthProvider>
      </QueryClientProvider>,
    )

    await user.click(await screen.findByRole('button', { name: 'Nova chat' }))
    await user.click(screen.getByRole('checkbox', { name: 'beto' }))
    await user.click(screen.getByRole('button', { name: 'Criar' }))

    expect(await screen.findByText('Chat view')).toBeInTheDocument()
  })
})
