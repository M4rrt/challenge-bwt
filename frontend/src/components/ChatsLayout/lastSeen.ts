function key(userId: string, chatId: string): string {
  return `chat-app:lastSeen:${userId}:${chatId}`
}

export function getLastSeenAt(userId: string, chatId: string): string | null {
  return localStorage.getItem(key(userId, chatId))
}

export function setLastSeenAt(
  userId: string,
  chatId: string,
  lastMessageAt: string | null,
): void {
  localStorage.setItem(key(userId, chatId), lastMessageAt ?? new Date().toISOString())
}

export function hasNewActivity(
  userId: string,
  chat: { id: string; last_message_at: string | null },
): boolean {
  if (!chat.last_message_at) {
    return false
  }
  const lastSeenAt = getLastSeenAt(userId, chat.id)
  if (lastSeenAt === null) {
    return false
  }
  return new Date(chat.last_message_at) > new Date(lastSeenAt)
}
