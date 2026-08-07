import type { Message } from './api'

export interface MessageGroup {
  senderId: string | null
  displayName: string
  timestamp: string
  messages: Message[]
}

function displayNameFor(message: Message, usernameById: Map<string, string>): string {
  if (message.sender_id) {
    return usernameById.get(message.sender_id) ?? 'Usuário'
  }
  return message.source_label ?? 'Bot'
}

function formatTimestamp(createdAt: string): string {
  return new Date(createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export function groupMessages(
  messages: Message[],
  usernameById: Map<string, string>,
): MessageGroup[] {
  const groups: MessageGroup[] = []

  for (const message of messages) {
    const previous = groups.at(-1)
    if (previous && previous.senderId === message.sender_id) {
      previous.messages.push(message)
      continue
    }
    groups.push({
      senderId: message.sender_id,
      displayName: displayNameFor(message, usernameById),
      timestamp: formatTimestamp(message.created_at),
      messages: [message],
    })
  }

  return groups
}
