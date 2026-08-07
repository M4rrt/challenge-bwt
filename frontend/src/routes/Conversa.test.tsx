import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from '../lib/auth/AuthContext'
import { getMe, listMessages, listUsers, sendMessage } from '../lib/api'
import Conversa from './Conversa'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    getMe: vi.fn(),
    listUsers: vi.fn(),
    listMessages: vi.fn(),
    sendMessage: vi.fn(),
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
]

function renderConversa() {
  const queryClient = new QueryClient()
  localStorage.setItem('chat-app:token', 'token-123')
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter initialEntries={['/conversas/conv-1']}>
          <Routes>
            <Route path="/conversas/:conversationId" element={<Conversa />} />
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
  vi.mocked(listUsers).mockReset().mockResolvedValue(USERS)
  vi.mocked(listMessages).mockReset()
  vi.mocked(sendMessage).mockReset()
})

describe('Conversa', () => {
  it('renders the message backlog on open', async () => {
    vi.mocked(listMessages).mockResolvedValue([
      {
        id: 'msg-1',
        conversation_id: 'conv-1',
        sender_id: 'beto-id',
        sender_type: 'user',
        source_label: null,
        body: 'oi ana',
        created_at: '2026-08-06T12:00:00Z',
      },
    ])
    renderConversa()

    expect(await screen.findByText('oi ana')).toBeInTheDocument()
  })

  it('shows a message pushed over the websocket without refetching the backlog', async () => {
    vi.mocked(listMessages).mockResolvedValue([])
    renderConversa()

    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1))
    expect(listMessages).toHaveBeenCalledTimes(1)

    const socket = FakeWebSocket.instances[0]
    socket.onmessage?.({
      data: JSON.stringify({
        id: 'msg-2',
        conversation_id: 'conv-1',
        sender_id: 'beto-id',
        sender_type: 'user',
        source_label: null,
        body: 'chegou ao vivo',
        created_at: '2026-08-06T12:01:00Z',
      }),
    })

    expect(await screen.findByText('chegou ao vivo')).toBeInTheDocument()
    expect(listMessages).toHaveBeenCalledTimes(1)
  })

  it('only shows a sent message once the REST response resolves, no optimistic add', async () => {
    vi.mocked(listMessages).mockResolvedValue([])
    let resolveSend: (value: Awaited<ReturnType<typeof sendMessage>>) => void = () => {}
    vi.mocked(sendMessage).mockReturnValue(
      new Promise((resolve) => {
        resolveSend = resolve
      }),
    )
    const user = userEvent.setup()
    renderConversa()

    const input = await screen.findByRole('textbox')
    await user.type(input, 'oi beto{Enter}')

    expect(sendMessage).toHaveBeenCalledWith('conv-1', 'oi beto', 'token-123')
    expect(screen.queryByText('oi beto')).not.toBeInTheDocument()

    resolveSend({
      id: 'msg-3',
      conversation_id: 'conv-1',
      sender_id: 'me-id',
      sender_type: 'user',
      source_label: null,
      body: 'oi beto',
      created_at: '2026-08-06T12:02:00Z',
    })

    expect(await screen.findByText('oi beto')).toBeInTheDocument()
  })
})
