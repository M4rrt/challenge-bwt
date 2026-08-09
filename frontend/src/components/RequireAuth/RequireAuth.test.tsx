import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AuthProvider } from '../../lib/auth/AuthContext'
import RequireAuth from './RequireAuth'

beforeEach(() => {
  localStorage.clear()
})

function renderWithRouter(initialPath: string) {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/" element={<div>Login page</div>} />
          <Route element={<RequireAuth />}>
            <Route path="/protected" element={<div>Protected content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  )
}

describe('RequireAuth', () => {
  it('redirects to / when there is no token', () => {
    renderWithRouter('/protected')

    expect(screen.getByText('Login page')).toBeInTheDocument()
  })

  it('renders the protected content when a token is present', () => {
    localStorage.setItem('chat-app:token', 'existing-token')

    renderWithRouter('/protected')

    expect(screen.getByText('Protected content')).toBeInTheDocument()
  })
})
