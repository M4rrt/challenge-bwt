import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from '../lib/auth/AuthContext'
import { createConversation, getMe, listConversations, listUsers } from '../lib/api'
import Conversas from './Conversas'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    getMe: vi.fn(),
    listUsers: vi.fn(),
    listConversations: vi.fn(),
    createConversation: vi.fn(),
  }
})

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
            <Route path="/conversas" element={<Conversas />} />
            <Route path="/login" element={<div>Login page</div>} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  localStorage.clear()
  vi.mocked(getMe).mockReset()
  vi.mocked(listUsers).mockReset()
  vi.mocked(listConversations).mockReset()
  vi.mocked(createConversation).mockReset()

  vi.mocked(getMe).mockResolvedValue(ME)
  vi.mocked(listUsers).mockResolvedValue(USERS)
})

describe('Conversas', () => {
  it("renders the user's conversations, resolving 1:1s to the other participant's username", async () => {
    vi.mocked(listConversations).mockResolvedValue([
      { id: 'conv-1', name: null, participant_user_ids: ['me-id', 'beto-id'] },
      { id: 'conv-2', name: 'Trio', participant_user_ids: ['me-id', 'beto-id', 'carla-id'] },
    ])
    renderConversas()

    expect(await screen.findByText('beto')).toBeInTheDocument()
    expect(await screen.findByText('Trio')).toBeInTheDocument()
  })

  it('requires a name before creating a group conversation', async () => {
    vi.mocked(listConversations).mockResolvedValue([])
    const user = userEvent.setup()
    renderConversas()

    await user.click(await screen.findByRole('button', { name: 'Nova conversa' }))
    await user.click(screen.getByRole('checkbox', { name: 'beto' }))
    await user.click(screen.getByRole('checkbox', { name: 'carla' }))

    expect(screen.getByLabelText('Nome do grupo')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Criar' }))

    expect(createConversation).not.toHaveBeenCalled()

    await user.type(screen.getByLabelText('Nome do grupo'), 'Trio')
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
})
