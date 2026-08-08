import { describe, expect, it } from 'vitest'
import type { Conversation } from './api'
import { conversationLabel } from './conversationLabel'

function makeConversation(overrides: Partial<Conversation>): Conversation {
  return {
    id: 'conv-1',
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

describe('conversationLabel', () => {
  it('uses the conversation name when it has one (named/group conversation)', () => {
    const conversation = makeConversation({ name: 'Trio' })

    expect(conversationLabel(conversation, 'me-id', usernameById)).toBe('Trio')
  })

  it('resolves to the other participant\'s username for an unnamed 1:1 conversation', () => {
    const conversation = makeConversation({ name: null })

    expect(conversationLabel(conversation, 'me-id', usernameById)).toBe('beto')
  })

  it('falls back to "Conversa" when the other participant is unknown', () => {
    const conversation = makeConversation({ name: null, participant_user_ids: ['me-id', 'unknown-id'] })

    expect(conversationLabel(conversation, 'me-id', usernameById)).toBe('Conversa')
  })

  it('does not fall back to the first participant when currentUserId is not yet known', () => {
    const conversation = makeConversation({ name: null, participant_user_ids: ['beto-id', 'me-id'] })

    expect(conversationLabel(conversation, undefined, usernameById)).toBe('Nova Conversa')
  })
})
