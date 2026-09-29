import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from '../../../lib/auth/AuthContext'
import { ApiError } from '../../../lib/api'
import type { Contact } from '../../../lib/monolith'
import { createChat, listContacts } from '../../../lib/monolith'
import StartChat from './StartChat'

vi.mock('../../../lib/monolith', async () => {
  const actual = await vi.importActual<typeof import('../../../lib/monolith')>('../../../lib/monolith')
  return {
    ...actual,
    listContacts: vi.fn(),
    createChat: vi.fn(),
  }
})

function contact(overrides: Partial<Contact>): Contact {
  return { id: 'user-1', display_name: 'Beto', avatar_url: null, kind: 'staff', ...overrides }
}

function renderStartChat() {
  localStorage.setItem('chat-app:token', 'token-123')
  localStorage.setItem('chat-app:renewal-token', 'renewal-123')
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <AuthProvider>
        <MemoryRouter initialEntries={['/chats']}>
          <Routes>
            <Route path="/chats" element={<StartChat />} />
            <Route path="/chats/:chatId" element={<div>Thread for chat</div>} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  localStorage.clear()
  vi.mocked(listContacts).mockReset().mockResolvedValue([])
  vi.mocked(createChat).mockReset()
})

describe('StartChat', () => {
  it('opens the picker and lists contacts from the monolith', async () => {
    vi.mocked(listContacts).mockResolvedValue([
      contact({}),
      contact({ id: 'user-2', display_name: 'Carla' }),
    ])
    const user = userEvent.setup()
    renderStartChat()

    await user.click(screen.getByRole('button', { name: 'Iniciar novo chat' }))

    expect(await screen.findByText('Beto')).toBeInTheDocument()
    expect(screen.getByText('Carla')).toBeInTheDocument()
  })

  it('submits with exactly one participant and no name, then navigates to the new chat', async () => {
    vi.mocked(listContacts).mockResolvedValue([contact({})])
    vi.mocked(createChat).mockResolvedValue({ chat_id: 'chat-9' })
    const user = userEvent.setup()
    renderStartChat()

    await user.click(screen.getByRole('button', { name: 'Iniciar novo chat' }))
    await user.click(await screen.findByText('Beto'))
    await user.click(screen.getByRole('button', { name: 'Iniciar chat' }))

    await waitFor(() => expect(createChat).toHaveBeenCalledWith('renewal-123', ['user-1'], undefined))
    expect(await screen.findByText('Thread for chat')).toBeInTheDocument()
  })

  it('disables submit when more than one participant is picked and no name is given', async () => {
    vi.mocked(listContacts).mockResolvedValue([
      contact({}),
      contact({ id: 'user-2', display_name: 'Carla' }),
    ])
    const user = userEvent.setup()
    renderStartChat()

    await user.click(screen.getByRole('button', { name: 'Iniciar novo chat' }))
    await user.click(await screen.findByText('Beto'))
    await user.click(screen.getByText('Carla'))

    expect(screen.getByRole('button', { name: 'Iniciar chat' })).toBeDisabled()
  })

  it('submits a group with a name once more than one participant is picked', async () => {
    vi.mocked(listContacts).mockResolvedValue([
      contact({}),
      contact({ id: 'user-2', display_name: 'Carla' }),
    ])
    vi.mocked(createChat).mockResolvedValue({ chat_id: 'chat-9' })
    const user = userEvent.setup()
    renderStartChat()

    await user.click(screen.getByRole('button', { name: 'Iniciar novo chat' }))
    await user.click(await screen.findByText('Beto'))
    await user.click(screen.getByText('Carla'))
    await user.type(screen.getByLabelText('Nome do grupo', { exact: false }), 'Trio')
    await user.click(screen.getByRole('button', { name: 'Iniciar chat' }))

    await waitFor(() =>
      expect(createChat).toHaveBeenCalledWith('renewal-123', ['user-1', 'user-2'], 'Trio'),
    )
  })

  it('shows a monolith rejection without crashing the picker or losing the current selection', async () => {
    vi.mocked(listContacts).mockResolvedValue([contact({})])
    vi.mocked(createChat).mockRejectedValue(new ApiError(422, { detail: 'não é um contato ativo' }))
    const user = userEvent.setup()
    renderStartChat()

    await user.click(screen.getByRole('button', { name: 'Iniciar novo chat' }))
    await user.click(await screen.findByText('Beto'))
    await user.click(screen.getByRole('button', { name: 'Iniciar chat' }))

    expect(await screen.findByText('não é um contato ativo')).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'Beto' })).toBeChecked()
  })
})
