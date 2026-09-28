import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from '../../lib/auth/AuthContext'
import { ApiError } from '../../lib/api'
import { issueChatToken, redeemExchangeCode } from '../../lib/monolith'
import SessionHandoff from './SessionHandoff'

vi.mock('../../lib/monolith', async () => {
  const actual = await vi.importActual<typeof import('../../lib/monolith')>('../../lib/monolith')
  return { ...actual, redeemExchangeCode: vi.fn(), issueChatToken: vi.fn() }
})

function renderSessionHandoff(initialPath: string) {
  const queryClient = new QueryClient()
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter initialEntries={[initialPath]}>
          <Routes>
            <Route path="/" element={<SessionHandoff />} />
            <Route path="/chats" element={<div>Chats page</div>} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  localStorage.clear()
  vi.mocked(redeemExchangeCode).mockReset()
  vi.mocked(issueChatToken).mockReset()
})

afterEach(() => {
  window.location.hash = ''
})

describe('SessionHandoff', () => {
  it('shows an error and never navigates when the URL fragment carries no code', async () => {
    renderSessionHandoff('/')

    expect(await screen.findByRole('alert')).toHaveTextContent(/nenhum código de sessão/i)
    expect(redeemExchangeCode).not.toHaveBeenCalled()
    expect(screen.queryByText('Chats page')).not.toBeInTheDocument()
    expect(localStorage.getItem('chat-app:token')).toBeNull()
  })

  it('redeems the code from the fragment, buys a chat token, stores everything and lands on /chats', async () => {
    vi.mocked(redeemExchangeCode).mockResolvedValue({
      renewal_token: 'renewal-123',
      api_url: 'https://chat.example.com',
      ws_url: 'wss://chat.example.com',
    })
    vi.mocked(issueChatToken).mockResolvedValue({ access_token: 'chat-token-123', token_type: 'bearer' })
    window.location.hash = '#code=exchange-abc'

    renderSessionHandoff('/')

    await waitFor(() => expect(screen.getByText('Chats page')).toBeInTheDocument())
    expect(redeemExchangeCode).toHaveBeenCalledWith('exchange-abc')
    expect(issueChatToken).toHaveBeenCalledWith('renewal-123')
    expect(localStorage.getItem('chat-app:token')).toBe('chat-token-123')
    expect(localStorage.getItem('chat-app:renewal-token')).toBe('renewal-123')
    expect(localStorage.getItem('chat-app:api-url')).toBe('https://chat.example.com')
  })

  it('strips the code from the URL fragment immediately, before redemption resolves', async () => {
    vi.mocked(redeemExchangeCode).mockResolvedValue({
      renewal_token: 'renewal-123',
      api_url: 'https://chat.example.com',
      ws_url: 'wss://chat.example.com',
    })
    vi.mocked(issueChatToken).mockResolvedValue({ access_token: 'chat-token-123', token_type: 'bearer' })
    window.location.hash = '#code=exchange-abc'

    renderSessionHandoff('/')

    expect(window.location.hash).toBe('')
  })

  it('shows an error and stores nothing when the exchange code is invalid or already used', async () => {
    vi.mocked(redeemExchangeCode).mockRejectedValue(new ApiError(401, { detail: 'code already used' }))
    window.location.hash = '#code=stale-code'

    renderSessionHandoff('/')

    expect(await screen.findByRole('alert')).toHaveTextContent(/expirou ou já foi usado/i)
    expect(issueChatToken).not.toHaveBeenCalled()
    expect(screen.queryByText('Chats page')).not.toBeInTheDocument()
    expect(localStorage.getItem('chat-app:token')).toBeNull()
    expect(localStorage.getItem('chat-app:renewal-token')).toBeNull()
  })

  it('shows an error and stores nothing when redemption succeeds but the token purchase fails', async () => {
    vi.mocked(redeemExchangeCode).mockResolvedValue({
      renewal_token: 'renewal-123',
      api_url: 'https://chat.example.com',
      ws_url: 'wss://chat.example.com',
    })
    vi.mocked(issueChatToken).mockRejectedValue(new ApiError(503, { detail: 'unavailable' }))
    window.location.hash = '#code=exchange-abc'

    renderSessionHandoff('/')

    expect(await screen.findByRole('alert')).toHaveTextContent(/expirou ou já foi usado/i)
    expect(screen.queryByText('Chats page')).not.toBeInTheDocument()
    expect(localStorage.getItem('chat-app:token')).toBeNull()
    expect(localStorage.getItem('chat-app:renewal-token')).toBeNull()
  })

  it('redirects straight to /chats without redeeming anything when already authenticated', () => {
    localStorage.setItem('chat-app:token', 'existing-token')
    localStorage.setItem('chat-app:renewal-token', 'existing-renewal-token')

    renderSessionHandoff('/')

    expect(screen.getByText('Chats page')).toBeInTheDocument()
    expect(redeemExchangeCode).not.toHaveBeenCalled()
  })
})
