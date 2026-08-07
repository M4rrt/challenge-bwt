import type { Message } from './api'

export type SenderKind = 'me' | 'other' | 'external'

export interface MessageGroup {
  groupKey: string | null
  displayName: string
  timestamp: string
  senderKind: SenderKind
  messages: Message[]
}

function displayNameFor(message: Message, usernameById: Map<string, string>): string {
  if (message.sender_id) {
    return usernameById.get(message.sender_id) ?? 'Usuário'
  }
  return message.source_label ?? 'Bot'
}

function groupKeyFor(message: Message): string | null {
  return message.sender_id ?? message.source_label
}

function senderKindFor(message: Message, currentUserId: string | undefined): SenderKind {
  if (!message.sender_id) {
    return 'external'
  }
  return message.sender_id === currentUserId ? 'me' : 'other'
}

function formatTimestamp(createdAt: string): string {
  return new Date(createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export function groupMessages(
  messages: Message[],
  usernameById: Map<string, string>,
  currentUserId?: string,
): MessageGroup[] {
  const groups: MessageGroup[] = []

  for (const message of messages) {
    const previous = groups.at(-1)
    const groupKey = groupKeyFor(message)
    if (previous && previous.groupKey === groupKey) {
      previous.messages.push(message)
      continue
    }
    groups.push({
      groupKey,
      displayName: displayNameFor(message, usernameById),
      timestamp: formatTimestamp(message.created_at),
      senderKind: senderKindFor(message, currentUserId),
      messages: [message],
    })
  }

  return groups
}
