import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from '../../../lib/auth/AuthContext'
import { createConversation, getMe, listConversations, listUsers } from '../../../lib/api'
import Sidebar from './Sidebar'

vi.mock('../../../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../../../lib/api')>('../../../lib/api')
  return {
    ...actual,
    getMe: vi.fn(),
    listUsers: vi.fn(),
    listConversations: vi.fn(),
    createConversation: vi.fn(),
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

function renderConversas() {
  const queryClient = new QueryClient()
  localStorage.setItem('chat-app:token', 'token-123')
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter initialEntries={['/conversas']}>
          <Routes>
            <Route path="/conversas" element={<Sidebar />} />
            <Route path="/conversas/:conversationId" element={<Sidebar />} />
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
  vi.mocked(listConversations).mockReset()
  vi.mocked(createConversation).mockReset()

  vi.mocked(getMe).mockResolvedValue(ME)
  vi.mocked(listUsers).mockResolvedValue(USERS)
})

describe('Sidebar', () => {
  it('shows the conversation count in the list header', async () => {
    vi.mocked(listConversations).mockResolvedValue([
      { id: 'conv-1', name: null, participant_user_ids: ['me-id', 'beto-id'], last_message_at: null },
      {
        id: 'conv-2',
        name: 'Trio',
        participant_user_ids: ['me-id', 'beto-id', 'carla-id'],
        last_message_at: null,
      },
    ])
    renderConversas()

    expect(await screen.findByRole('heading', { name: 'Conversas (2)' })).toBeInTheDocument()
  })

  it("renders the user's conversations, resolving 1:1s to the other participant's username", async () => {
    vi.mocked(listConversations).mockResolvedValue([
      { id: 'conv-1', name: null, participant_user_ids: ['me-id', 'beto-id'], last_message_at: null },
      {
        id: 'conv-2',
        name: 'Trio',
        participant_user_ids: ['me-id', 'beto-id', 'carla-id'],
        last_message_at: null,
      },
    ])
    renderConversas()

    expect(await screen.findByText('beto')).toBeInTheDocument()
    expect(await screen.findByText('Trio')).toBeInTheDocument()
  })

  it('shows a person icon for a 1:1 item and a group icon for a group item', async () => {
    vi.mocked(listConversations).mockResolvedValue([
      { id: 'conv-1', name: null, participant_user_ids: ['me-id', 'beto-id'], last_message_at: null },
      {
        id: 'conv-2',
        name: 'Trio',
        participant_user_ids: ['me-id', 'beto-id', 'carla-id'],
        last_message_at: null,
      },
    ])
    renderConversas()

    await screen.findByText('beto')
    expect(screen.getByLabelText('Conversa individual')).toBeInTheDocument()
    expect(screen.getByLabelText('Conversa em grupo')).toBeInTheDocument()
  })

  it('renders the "Nova conversa" button before the conversation list', async () => {
    vi.mocked(listConversations).mockResolvedValue([
      { id: 'conv-1', name: null, participant_user_ids: ['me-id', 'beto-id'], last_message_at: null },
    ])
    renderConversas()

    const button = await screen.findByRole('button', { name: 'Nova conversa' })
    const item = await screen.findByText('beto')

    expect(button.compareDocumentPosition(item) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('refetches the user list when opening the new-conversation form', async () => {
    vi.mocked(listConversations).mockResolvedValue([])
    const user = userEvent.setup()
    renderConversas()

    await waitFor(() => expect(listUsers).toHaveBeenCalledTimes(1))

    await user.click(await screen.findByRole('button', { name: 'Nova conversa' }))

    await waitFor(() => expect(listUsers).toHaveBeenCalledTimes(2))
  })

  it('requires a name before creating a group conversation', async () => {
    vi.mocked(listConversations).mockResolvedValue([])
    const user = userEvent.setup()
    renderConversas()

    await user.click(await screen.findByRole('button', { name: 'Nova conversa' }))
    await user.click(screen.getByRole('checkbox', { name: 'beto' }))
    await user.click(screen.getByRole('checkbox', { name: 'carla' }))

    expect(screen.getByPlaceholderText(/Nome do Grupo/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Criar' }))

    expect(createConversation).not.toHaveBeenCalled()

    await user.type(screen.getByPlaceholderText(/Nome do Grupo/i), 'Trio')
    await user.click(screen.getByRole('button', { name: 'Criar' }))

    await waitFor(() =>
      expect(createConversation).toHaveBeenCalledWith(
        ['beto-id', 'carla-id'],
        'Trio',
        'token-123',
      ),
    )
  })

  it('does not duplicate an existing 1:1 conversation when the same contact is picked again', async () => {
    // listConversations always resolves to this same single-item array, so this would
    // fail if the create mutation appended its response into the list locally instead
    // of relying on the (idempotent) backend + a refetch.
    const existingConversation = {
      id: 'conv-1',
      name: null,
      participant_user_ids: ['me-id', 'beto-id'],
      last_message_at: null,
    }
    vi.mocked(listConversations).mockResolvedValue([existingConversation])
    vi.mocked(createConversation).mockResolvedValue(existingConversation)
    const user = userEvent.setup()
    renderConversas()

    expect(await screen.findByText('beto')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Nova conversa' }))
    await user.click(screen.getByRole('checkbox', { name: 'beto' }))
    await user.click(screen.getByRole('button', { name: 'Criar' }))

    await waitFor(() => expect(createConversation).toHaveBeenCalledWith(['beto-id'], undefined, 'token-123'))
    expect(await screen.findAllByText('beto')).toHaveLength(1)
  })

  it('refetches the conversation list when the user-channel socket receives a message', async () => {
    vi.mocked(listConversations).mockResolvedValue([])
    renderConversas()

    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1))
    expect(FakeWebSocket.instances[0].url).toContain('/websocket/users/me?token=token-123')
    expect(listConversations).toHaveBeenCalledTimes(1)

    FakeWebSocket.instances[0].onmessage?.({ data: '{}' })

    await waitFor(() => expect(listConversations).toHaveBeenCalledTimes(2))
  })

  it('shows a new-activity indicator for a conversation with a message newer than the last-seen cursor', async () => {
    localStorage.setItem('chat-app:lastSeen:me-id:conv-1', '2026-08-06T12:00:00Z')
    vi.mocked(listConversations).mockResolvedValue([
      {
        id: 'conv-1',
        name: null,
        participant_user_ids: ['me-id', 'beto-id'],
        last_message_at: '2026-08-06T12:05:00Z',
      },
    ])
    renderConversas()

    expect(await screen.findByLabelText('Nova atividade')).toBeInTheDocument()
  })

  it('does not show a new-activity indicator when the last-seen cursor is already current', async () => {
    localStorage.setItem('chat-app:lastSeen:me-id:conv-1', '2026-08-06T12:05:00Z')
    vi.mocked(listConversations).mockResolvedValue([
      {
        id: 'conv-1',
        name: null,
        participant_user_ids: ['me-id', 'beto-id'],
        last_message_at: '2026-08-06T12:05:00Z',
      },
    ])
    renderConversas()

    await screen.findByText('beto')
    expect(screen.queryByLabelText('Nova atividade')).not.toBeInTheDocument()
  })

  it('does not show a new-activity indicator when there is no stored cursor (cold start)', async () => {
    vi.mocked(listConversations).mockResolvedValue([
      {
        id: 'conv-1',
        name: null,
        participant_user_ids: ['me-id', 'beto-id'],
        last_message_at: '2026-08-06T12:05:00Z',
      },
    ])
    renderConversas()

    await screen.findByText('beto')
    expect(screen.queryByLabelText('Nova atividade')).not.toBeInTheDocument()
  })

  it('does not show a new-activity indicator for the conversation currently open', async () => {
    localStorage.setItem('chat-app:lastSeen:me-id:conv-1', '2026-08-06T12:00:00Z')
    vi.mocked(listConversations).mockResolvedValue([
      {
        id: 'conv-1',
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
          <MemoryRouter initialEntries={['/conversas/conv-1']}>
            <Routes>
              <Route path="/conversas/:conversationId" element={<Sidebar />} />
            </Routes>
          </MemoryRouter>
        </AuthProvider>
      </QueryClientProvider>,
    )

    await screen.findByText('beto')
    expect(screen.queryByLabelText('Nova atividade')).not.toBeInTheDocument()
  })

  it('navigates to the new conversation after creating it', async () => {
    vi.mocked(listConversations).mockResolvedValue([])
    const newConversation = {
      id: 'conv-new',
      name: null,
      participant_user_ids: ['me-id', 'beto-id'],
      last_message_at: null,
    }
    vi.mocked(createConversation).mockResolvedValue(newConversation)
    const user = userEvent.setup()
    const queryClient = new QueryClient()
    localStorage.setItem('chat-app:token', 'token-123')
    render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <MemoryRouter initialEntries={['/conversas']}>
            <Routes>
              <Route path="/conversas" element={<Sidebar />} />
              <Route path="/conversas/:conversationId" element={<div>Conversation view</div>} />
            </Routes>
          </MemoryRouter>
        </AuthProvider>
      </QueryClientProvider>,
    )

    await user.click(await screen.findByRole('button', { name: 'Nova conversa' }))
    await user.click(screen.getByRole('checkbox', { name: 'beto' }))
    await user.click(screen.getByRole('button', { name: 'Criar' }))

    expect(await screen.findByText('Conversation view')).toBeInTheDocument()
  })
})
