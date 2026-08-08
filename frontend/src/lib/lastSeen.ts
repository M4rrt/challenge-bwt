function key(userId: string, conversationId: string): string {
  return `chat-app:lastSeen:${userId}:${conversationId}`
}

export function getLastSeenAt(userId: string, conversationId: string): string | null {
  return localStorage.getItem(key(userId, conversationId))
}

export function setLastSeenAt(
  userId: string,
  conversationId: string,
  lastMessageAt: string | null,
): void {
  localStorage.setItem(key(userId, conversationId), lastMessageAt ?? new Date().toISOString())
}

export function hasNewActivity(
  userId: string,
  conversation: { id: string; last_message_at: string | null },
): boolean {
  if (!conversation.last_message_at) {
    return false
  }
  const lastSeenAt = getLastSeenAt(userId, conversation.id)
  if (lastSeenAt === null) {
    return false
  }
  return new Date(conversation.last_message_at) > new Date(lastSeenAt)
}
