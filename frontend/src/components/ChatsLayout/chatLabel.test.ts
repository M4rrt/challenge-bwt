import { describe, expect, it } from 'vitest'
import type { Chat, Message } from '../../lib/api'
import { chatLabel } from './chatLabel'

function makeMessage(overrides: Partial<Message>): Message {
  return {
    id: 'msg-1',
    chat_id: 'chat-1',
    sender_id: null,
    sender_type: 'user',
    source_label: null,
    body: 'oi',
    created_at: '2026-08-06T12:00:00Z',
    ...overrides,
  }
}

function makeChat(overrides: Partial<Chat>): Chat {
  return {
    id: 'chat-1',
    type: 'staff',
    name: null,
    participant_user_ids: ['me-id', 'beto-id'],
    last_message: null,
    last_message_at: null,
    unread_count: 0,
    last_read_at: null,
    last_read_message_id: null,
    ...overrides,
  }
}

describe('chatLabel', () => {
  it('uses the chat name when it has one (named/group chat)', () => {
    const chat = makeChat({ name: 'Trio' })

    expect(chatLabel(chat, 'me-id')).toBe('Trio')
  })

  it("resolves to the other participant's display name off their last message, for an unnamed 1:1 chat", () => {
    const chat = makeChat({
      name: null,
      last_message: makeMessage({ sender_id: 'beto-id', sender_display_name: 'Beto' }),
    })

    expect(chatLabel(chat, 'me-id')).toBe('Beto')
  })

  it("falls back to a placeholder when the last message was mine, not the other participant's", () => {
    const chat = makeChat({
      name: null,
      last_message: makeMessage({ sender_id: 'me-id', sender_display_name: 'Ana' }),
    })

    expect(chatLabel(chat, 'me-id')).toBe('Novo Chat')
  })

  it('falls back to a placeholder when there is no message yet', () => {
    const chat = makeChat({ name: null, last_message: null })

    expect(chatLabel(chat, 'me-id')).toBe('Novo Chat')
  })

  it('does not fall back to the first participant when currentUserId is not yet known', () => {
    const chat = makeChat({ name: null, participant_user_ids: ['beto-id', 'me-id'] })

    expect(chatLabel(chat, undefined)).toBe('Novo Chat')
  })
})
