import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from '../lib/auth/AuthContext'
import { getMe, listConversations, listMessages, listUsers } from '../lib/api'
import ConversasLayout from './ConversasLayout'
import ConversaEmptyState from './ConversaEmptyState'
import Conversa from './Conversa'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    getMe: vi.fn(),
    listUsers: vi.fn(),
    listConversations: vi.fn(),
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
  vi.mocked(listConversations).mockReset().mockResolvedValue([])
  vi.mocked(listMessages).mockReset().mockResolvedValue([])
})

describe('ConversasLayout', () => {
  it('renders the empty-state placeholder when no conversation is selected', async () => {
    const queryClient = new QueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <MemoryRouter initialEntries={['/conversas']}>
            <Routes>
              <Route path="/conversas" element={<ConversasLayout />}>
                <Route index element={<ConversaEmptyState />} />
              </Route>
            </Routes>
          </MemoryRouter>
        </AuthProvider>
      </QueryClientProvider>,
    )

    expect(await screen.findByText('Selecione uma conversa para começar')).toBeInTheDocument()
  })

  it('does not show a stale new-activity indicator on the conversation just left, after a live message arrived while it was open', async () => {
    vi.mocked(listConversations)
      .mockResolvedValueOnce([
        { id: 'conv-1', name: null, participant_user_ids: ['me-id', 'beto-id'], last_message_at: '2026-08-06T12:00:00Z' },
        { id: 'conv-2', name: null, participant_user_ids: ['me-id', 'carla-id'], last_message_at: null },
      ])
      .mockResolvedValue([
        { id: 'conv-1', name: null, participant_user_ids: ['me-id', 'beto-id'], last_message_at: '2026-08-06T12:05:00Z' },
        { id: 'conv-2', name: null, participant_user_ids: ['me-id', 'carla-id'], last_message_at: null },
      ])
    vi.mocked(listMessages).mockImplementation(async (conversationId: string) =>
      conversationId === 'conv-1'
        ? [
            {
              id: 'msg-1',
              conversation_id: 'conv-1',
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
          <MemoryRouter initialEntries={['/conversas/conv-1']}>
            <Routes>
              <Route path="/conversas" element={<ConversasLayout />}>
                <Route path=":conversationId" element={<Conversa />} />
              </Route>
            </Routes>
          </MemoryRouter>
        </AuthProvider>
      </QueryClientProvider>,
    )

    await screen.findByText('oi ana')
    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(2))

    const conversationSocket = FakeWebSocket.instances.find((instance) =>
      instance.url.includes('/websocket/conversations/'),
    )!
    const userSocket = FakeWebSocket.instances.find((instance) =>
      instance.url.includes('/websocket/users/me'),
    )!

    // A new message arrives in conv-1 while it's still open: the conversation
    // socket delivers it to Conversa, and the user socket tells Sidebar to
    // refetch, picking up the newer last_message_at from the mock above.
    conversationSocket.onmessage?.({
      data: JSON.stringify({
        id: 'msg-2',
        conversation_id: 'conv-1',
        sender_id: 'beto-id',
        sender_type: 'user',
        source_label: null,
        body: 'chegou ao vivo',
        created_at: '2026-08-06T12:05:00Z',
      }),
    })
    userSocket.onmessage?.({ data: '{}' })

    await waitFor(() => expect(listConversations).toHaveBeenCalledTimes(2))
    await screen.findByText('chegou ao vivo')

    await user.click(screen.getByText('carla'))

    expect(screen.queryByLabelText('Nova atividade')).not.toBeInTheDocument()
  })
})
