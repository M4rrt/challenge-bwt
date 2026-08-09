import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ApiError, register } from '../../lib/api'
import Register from './Register'

vi.mock('../../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../../lib/api')>('../../lib/api')
  return { ...actual, register: vi.fn() }
})

function renderRegister() {
  const queryClient = new QueryClient()
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/register']}>
        <Routes>
          <Route path="/register" element={<Register />} />
          <Route path="/" element={<div>Login page</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.mocked(register).mockReset()
})

describe('Register', () => {
  it('renders the messenger-themed titlebar and heading', () => {
    renderRegister()

    expect(screen.getByText('Criar nova conta no Chat-App')).toBeInTheDocument()
    expect(screen.getByText('Cadastro de Novo Usuário')).toBeInTheDocument()
    expect(screen.getByLabelText('Nome de Usuário (Nick do Chat-App)')).toBeInTheDocument()
  })

  it('navigates to / after a successful registration', async () => {
    vi.mocked(register).mockResolvedValue({ id: 'user-1', email: 'ana@example.com', username: 'ana' })
    const user = userEvent.setup()
    renderRegister()

    await user.type(screen.getByLabelText('E-mail'), 'ana@example.com')
    await user.type(screen.getByLabelText('Nome de Usuário (Nick do Chat-App)'), 'ana')
    await user.type(screen.getByLabelText('Senha'), 'Senha-Forte-123')
    await user.click(screen.getByRole('button', { name: 'Concluir Cadastro' }))

    expect(await screen.findByText('Login page')).toBeInTheDocument()
  })

  it('shows an error message and stays on the page when registration fails', async () => {
    vi.mocked(register).mockRejectedValue(new ApiError(409, { detail: 'email already registered' }))
    const user = userEvent.setup()
    renderRegister()

    await user.type(screen.getByLabelText('E-mail'), 'dup@example.com')
    await user.type(screen.getByLabelText('Nome de Usuário (Nick do Chat-App)'), 'dup')
    await user.type(screen.getByLabelText('Senha'), 'Senha-Forte-123')
    await user.click(screen.getByRole('button', { name: 'Concluir Cadastro' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Email já cadastrado')
    expect(screen.queryByText('Login page')).not.toBeInTheDocument()
  })

  it('shows a password policy message when the password is too weak', async () => {
    vi.mocked(register).mockRejectedValue(
      new ApiError(422, { detail: 'password must be at least 8 characters' }),
    )
    const user = userEvent.setup()
    renderRegister()

    await user.type(screen.getByLabelText('E-mail'), 'ana@example.com')
    await user.type(screen.getByLabelText('Nome de Usuário (Nick do Chat-App)'), 'ana')
    await user.type(screen.getByLabelText('Senha'), 'weak')
    await user.click(screen.getByRole('button', { name: 'Concluir Cadastro' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Senha deve ter pelo menos 8 caracteres, com maiúscula, minúscula e um número ou símbolo',
    )
    expect(screen.queryByText('Login page')).not.toBeInTheDocument()
  })

  it('links back to the login screen', () => {
    renderRegister()

    expect(screen.getByRole('link', { name: 'Ir para Tela de Login' })).toHaveAttribute('href', '/')
  })
})
