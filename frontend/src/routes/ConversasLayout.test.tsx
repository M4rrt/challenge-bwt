import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from '../lib/auth/AuthContext'
import { getMe, listConversations, listUsers } from '../lib/api'
import ConversasLayout from './ConversasLayout'
import ConversaEmptyState from './ConversaEmptyState'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    getMe: vi.fn(),
    listUsers: vi.fn(),
    listConversations: vi.fn(),
  }
})

beforeEach(() => {
  localStorage.clear()
  localStorage.setItem('chat-app:token', 'token-123')
  vi.mocked(getMe).mockReset().mockResolvedValue({
    id: 'me-id',
    email: 'ana@example.com',
    username: 'ana',
  })
  vi.mocked(listUsers).mockReset().mockResolvedValue([])
  vi.mocked(listConversations).mockReset().mockResolvedValue([])
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
})
