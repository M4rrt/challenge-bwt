import type { Chat } from '../../lib/api'

export function chatLabel(
  chat: Chat,
  currentUserId: string | undefined,
  usernameById: Map<string, string>,
): string {
  if (chat.name) {
    return chat.name
  }
  if (currentUserId === undefined) {
    return 'Novo Chat'
  }
  const otherId = chat.participant_user_ids.find((id) => id !== currentUserId)
  return (otherId && usernameById.get(otherId)) ?? 'Chat'
}
