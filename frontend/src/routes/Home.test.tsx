import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from '../lib/auth/AuthContext'
import { ApiError, login } from '../lib/api'
import Home from './Home'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return { ...actual, login: vi.fn() }
})

function renderHome() {
  const queryClient = new QueryClient()
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter initialEntries={['/']}>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/conversas" element={<div>Conversas page</div>} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  localStorage.clear()
  vi.mocked(login).mockReset()
})

describe('Home', () => {
  it('renders the login form and links to /register', () => {
    renderHome()

    expect(screen.getByLabelText('Email')).toBeInTheDocument()
    expect(screen.getByLabelText('Senha')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Registrar' })).toHaveAttribute('href', '/register')
  })

  it('stores the token and navigates to /conversas on success', async () => {
    vi.mocked(login).mockResolvedValue({ access_token: 'token-123', token_type: 'bearer' })
    const user = userEvent.setup()
    renderHome()

    await user.type(screen.getByLabelText('Email'), 'ana@example.com')
    await user.type(screen.getByLabelText('Senha'), 'Senha-Forte-123')
    await user.click(screen.getByRole('button', { name: 'Entrar' }))

    await waitFor(() => expect(screen.getByText('Conversas page')).toBeInTheDocument())
    expect(localStorage.getItem('chat-app:token')).toBe('token-123')
  })

  it('shows an error message and does not navigate on invalid credentials', async () => {
    vi.mocked(login).mockRejectedValue(new ApiError(401, { detail: 'invalid credentials' }))
    const user = userEvent.setup()
    renderHome()

    await user.type(screen.getByLabelText('Email'), 'ana@example.com')
    await user.type(screen.getByLabelText('Senha'), 'wrong-password')
    await user.click(screen.getByRole('button', { name: 'Entrar' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Credenciais inválidas')
    expect(screen.queryByText('Conversas page')).not.toBeInTheDocument()
    expect(localStorage.getItem('chat-app:token')).toBeNull()
  })

  it('redirects to /conversas when already authenticated', () => {
    localStorage.setItem('chat-app:token', 'existing-token')

    renderHome()

    expect(screen.getByText('Conversas page')).toBeInTheDocument()
  })
})
