import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import Home from './Home'

describe('Home', () => {
  it('links to /login', () => {
    render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>,
    )

    expect(screen.getByRole('link', { name: 'Entrar' })).toHaveAttribute('href', '/login')
  })
})
