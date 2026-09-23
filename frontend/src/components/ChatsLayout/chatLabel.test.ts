import { describe, expect, it } from 'vitest'
import type { Chat } from '../../lib/api'
import { chatLabel } from './chatLabel'

function makeChat(overrides: Partial<Chat>): Chat {
  return {
    id: 'chat-1',
    name: null,
    participant_user_ids: ['me-id', 'beto-id'],
    last_message_at: null,
    ...overrides,
  }
}

const usernameById = new Map([
  ['me-id', 'ana'],
  ['beto-id', 'beto'],
])

describe('chatLabel', () => {
  it('uses the chat name when it has one (named/group chat)', () => {
    const chat = makeChat({ name: 'Trio' })

    expect(chatLabel(chat, 'me-id', usernameById)).toBe('Trio')
  })

  it('resolves to the other participant\'s username for an unnamed 1:1 chat', () => {
    const chat = makeChat({ name: null })

    expect(chatLabel(chat, 'me-id', usernameById)).toBe('beto')
  })

  it('falls back to "Chat" when the other participant is unknown', () => {
    const chat = makeChat({ name: null, participant_user_ids: ['me-id', 'unknown-id'] })

    expect(chatLabel(chat, 'me-id', usernameById)).toBe('Chat')
  })

  it('does not fall back to the first participant when currentUserId is not yet known', () => {
    const chat = makeChat({ name: null, participant_user_ids: ['beto-id', 'me-id'] })

    expect(chatLabel(chat, undefined, usernameById)).toBe('Novo Chat')
  })
})
