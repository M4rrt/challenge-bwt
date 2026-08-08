import type { Conversation } from './api'

export function conversationLabel(
  conversation: Conversation,
  currentUserId: string | undefined,
  usernameById: Map<string, string>,
): string {
  if (conversation.name) {
    return conversation.name
  }
  if (currentUserId === undefined) {
    return 'Nova Conversa'
  }
  const otherId = conversation.participant_user_ids.find((id) => id !== currentUserId)
  return (otherId && usernameById.get(otherId)) ?? 'Conversa'
}
