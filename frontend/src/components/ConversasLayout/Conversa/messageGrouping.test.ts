import { describe, expect, it } from 'vitest'
import type { Message } from '../../../lib/api'
import { groupMessages } from './messageGrouping'

function makeMessage(overrides: Partial<Message>): Message {
  return {
    id: 'msg-1',
    conversation_id: 'conv-1',
    sender_id: 'user-1',
    sender_type: 'user',
    source_label: null,
    body: 'oi',
    created_at: '2026-08-06T12:00:00Z',
    ...overrides,
  }
}

const usernameById = new Map([
  ['user-1', 'ana'],
  ['user-2', 'beto'],
])

describe('groupMessages', () => {
  it('collapses consecutive messages from the same sender into one group', () => {
    const messages = [
      makeMessage({ id: 'msg-1', sender_id: 'user-1' }),
      makeMessage({ id: 'msg-2', sender_id: 'user-1' }),
    ]

    const groups = groupMessages(messages, usernameById)

    expect(groups).toHaveLength(1)
    expect(groups[0].messages).toHaveLength(2)
    expect(groups[0].displayName).toBe('ana')
  })

  it('starts a new group when the sender changes', () => {
    const messages = [
      makeMessage({ id: 'msg-1', sender_id: 'user-1' }),
      makeMessage({ id: 'msg-2', sender_id: 'user-2' }),
    ]

    const groups = groupMessages(messages, usernameById)

    expect(groups).toHaveLength(2)
    expect(groups[0].displayName).toBe('ana')
    expect(groups[1].displayName).toBe('beto')
  })

  it('falls back to source_label when sender_id is null', () => {
    const messages = [
      makeMessage({ id: 'msg-1', sender_id: null, sender_type: 'external', source_label: 'Zapier' }),
    ]

    const groups = groupMessages(messages, usernameById)

    expect(groups[0].displayName).toBe('Zapier')
  })

  it('falls back to "Bot" when sender_id and source_label are both null', () => {
    const messages = [
      makeMessage({ id: 'msg-1', sender_id: null, sender_type: 'external', source_label: null }),
    ]

    const groups = groupMessages(messages, usernameById)

    expect(groups[0].displayName).toBe('Bot')
  })

  it('starts a new group when sender_id is null but source_label differs', () => {
    const messages = [
      makeMessage({
        id: 'msg-1',
        sender_id: null,
        sender_type: 'external',
        source_label: 'Insomnia Test',
      }),
      makeMessage({
        id: 'msg-2',
        sender_id: null,
        sender_type: 'external',
        source_label: 'Shipping Bot',
      }),
    ]

    const groups = groupMessages(messages, usernameById)

    expect(groups).toHaveLength(2)
    expect(groups[0].displayName).toBe('Insomnia Test')
    expect(groups[1].displayName).toBe('Shipping Bot')
  })

  it('marks a group as "me" when the message sender is the current user', () => {
    const messages = [makeMessage({ id: 'msg-1', sender_id: 'user-1' })]

    const groups = groupMessages(messages, usernameById, 'user-1')

    expect(groups[0].senderKind).toBe('me')
  })

  it('marks a group as "other" when the message sender is a different user', () => {
    const messages = [makeMessage({ id: 'msg-1', sender_id: 'user-2' })]

    const groups = groupMessages(messages, usernameById, 'user-1')

    expect(groups[0].senderKind).toBe('other')
  })

  it('marks a group as "external" when the message has no sender_id (webhook)', () => {
    const messages = [
      makeMessage({ id: 'msg-1', sender_id: null, sender_type: 'external', source_label: 'Zapier' }),
    ]

    const groups = groupMessages(messages, usernameById, 'user-1')

    expect(groups[0].senderKind).toBe('external')
  })

  it('takes the group timestamp from the first message in the group', () => {
    const messages = [
      makeMessage({ id: 'msg-1', sender_id: 'user-1', created_at: '2026-08-06T12:00:00Z' }),
      makeMessage({ id: 'msg-2', sender_id: 'user-1', created_at: '2026-08-06T12:05:00Z' }),
    ]

    const groups = groupMessages(messages, usernameById)

    expect(groups[0].timestamp).toBe(
      new Date('2026-08-06T12:00:00Z').toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    )
  })
})
