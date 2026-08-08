import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from '../lib/auth/AuthContext'
import { ApiError, getMe, sendWebhookMessage } from '../lib/api'
import WebhookTestPage from './WebhookTestPage'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return { ...actual, getMe: vi.fn(), sendWebhookMessage: vi.fn() }
})

function renderPage() {
  const queryClient = new QueryClient()
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter initialEntries={['/webhook']}>
          <Routes>
            <Route path="/webhook" element={<WebhookTestPage />} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  localStorage.clear()
  localStorage.setItem('chat-app:token', 'token-123')
  vi.stubEnv('VITE_WEBHOOK_TEST_SECRET', 'test-secret')
  vi.mocked(getMe).mockReset()
  vi.mocked(sendWebhookMessage).mockReset()
  vi.mocked(getMe).mockResolvedValue({ id: 'user-1', email: 'ana@example.com', username: 'ana' })
})

afterEach(() => {
  vi.unstubAllEnvs()
})

describe('WebhookTestPage', () => {
  it('shows the current username and the test disclaimer', async () => {
    renderPage()

    expect(await screen.findByText('ana')).toBeInTheDocument()
    expect(
      screen.getByText('essa é apenas uma pagina para teste do WebHook'),
    ).toBeInTheDocument()
  })

  it('signs and submits the form, showing the created message on success', async () => {
    vi.mocked(sendWebhookMessage).mockResolvedValue({
      id: 'msg-1',
      conversation_id: 'conv-1',
      sender_id: null,
      sender_type: 'external',
      source_label: 'crm',
      body: 'oi',
      created_at: '2026-08-06T12:00:00Z',
    })
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('ana')

    await user.type(screen.getByLabelText('Conversation ID'), 'conv-1')
    await user.type(screen.getByLabelText('Mensagem'), 'oi')
    await user.type(screen.getByLabelText('Nome do remetente'), 'crm')
    await user.click(screen.getByRole('button', { name: 'Enviar' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('msg-1')
    expect(sendWebhookMessage).toHaveBeenCalledWith(
      JSON.stringify({ conversation_id: 'conv-1', body: 'oi', source_label: 'crm' }),
      expect.any(String),
    )
  })

  it('shows the error detail when the webhook call is rejected', async () => {
    vi.mocked(sendWebhookMessage).mockRejectedValue(
      new ApiError(401, { detail: 'invalid signature' }),
    )
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('ana')

    await user.type(screen.getByLabelText('Conversation ID'), 'conv-1')
    await user.type(screen.getByLabelText('Mensagem'), 'oi')
    await user.click(screen.getByRole('button', { name: 'Enviar' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('invalid signature')
  })
})
