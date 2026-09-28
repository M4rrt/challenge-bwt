import type { Chat } from '../../lib/api'

const PLACEHOLDER = 'Novo Chat'

export function chatLabel(chat: Chat, currentUserId: string | undefined): string {
  if (chat.name) {
    return chat.name
  }
  if (currentUserId === undefined) {
    return PLACEHOLDER
  }
  const otherId = chat.participant_user_ids.find((id) => id !== currentUserId)
  const lastMessage = chat.last_message
  if (otherId && lastMessage?.sender_id === otherId && lastMessage.sender_display_name) {
    return lastMessage.sender_display_name
  }
  return PLACEHOLDER
}
