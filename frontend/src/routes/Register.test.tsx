import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { register } from '../lib/api'
import Register from './Register'

vi.mock('../lib/api')

function renderRegister() {
  const queryClient = new QueryClient()
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/register']}>
        <Routes>
          <Route path="/register" element={<Register />} />
          <Route path="/login" element={<div>Login page</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.mocked(register).mockReset()
})

describe('Register', () => {
  it('navigates to /login after a successful registration', async () => {
    vi.mocked(register).mockResolvedValue({ id: 'user-1', email: 'ana@example.com' })
    const user = userEvent.setup()
    renderRegister()

    await user.type(screen.getByLabelText('Email'), 'ana@example.com')
    await user.type(screen.getByLabelText('Senha'), 'Senha-Forte-123')
    await user.click(screen.getByRole('button', { name: 'Criar conta' }))

    expect(await screen.findByText('Login page')).toBeInTheDocument()
  })

  it('shows an error message and stays on the page when registration fails', async () => {
    vi.mocked(register).mockRejectedValue(new Error('email already registered'))
    const user = userEvent.setup()
    renderRegister()

    await user.type(screen.getByLabelText('Email'), 'dup@example.com')
    await user.type(screen.getByLabelText('Senha'), 'Senha-Forte-123')
    await user.click(screen.getByRole('button', { name: 'Criar conta' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Não foi possível criar a conta')
    expect(screen.queryByText('Login page')).not.toBeInTheDocument()
  })
})
