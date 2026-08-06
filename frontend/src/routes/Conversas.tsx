import type { FormEvent } from 'react'
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  type Conversation,
  createConversation,
  getMe,
  listConversations,
  listUsers,
} from '../lib/api'
import { useAuth } from '../lib/auth/AuthContext'

function conversationLabel(
  conversation: Conversation,
  currentUserId: string | undefined,
  usernameById: Map<string, string>,
): string {
  if (conversation.name) {
    return conversation.name
  }
  const otherId = conversation.participant_user_ids.find((id) => id !== currentUserId)
  return (otherId && usernameById.get(otherId)) ?? 'Conversa'
}

function Conversas() {
  const auth = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const token = auth.token ?? undefined

  const [isFormOpen, setIsFormOpen] = useState(false)
  const [selectedUserIds, setSelectedUserIds] = useState<string[]>([])
  const [groupName, setGroupName] = useState('')

  const meQuery = useQuery({ queryKey: ['me'], queryFn: () => getMe(token!), enabled: !!token })
  const usersQuery = useQuery({
    queryKey: ['users'],
    queryFn: () => listUsers(token!),
    enabled: !!token,
  })
  const conversationsQuery = useQuery({
    queryKey: ['conversations'],
    queryFn: () => listConversations(token!),
    enabled: !!token,
  })

  const createMutation = useMutation({
    mutationFn: () => createConversation(selectedUserIds, groupName || undefined, token!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] })
      setIsFormOpen(false)
      setSelectedUserIds([])
      setGroupName('')
    },
  })

  function handleLogout() {
    auth.logout()
    navigate('/login')
  }

  function toggleParticipant(userId: string) {
    setSelectedUserIds((current) =>
      current.includes(userId) ? current.filter((id) => id !== userId) : [...current, userId],
    )
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    createMutation.mutate()
  }

  const usernameById = new Map(usersQuery.data?.map((user) => [user.id, user.username]) ?? [])
  const otherUsers = usersQuery.data?.filter((user) => user.id !== meQuery.data?.id) ?? []
  const isGroup = selectedUserIds.length > 1

  return (
    <main>
      <h1>Conversas</h1>
      <ul>
        {conversationsQuery.data?.map((conversation) => (
          <li key={conversation.id}>
            {conversationLabel(conversation, meQuery.data?.id, usernameById)}
          </li>
        ))}
      </ul>
      {!isFormOpen && (
        <button type="button" onClick={() => setIsFormOpen(true)}>
          Nova conversa
        </button>
      )}
      {isFormOpen && (
        <form onSubmit={handleSubmit}>
          <fieldset>
            <legend>Participantes</legend>
            {otherUsers.map((user) => (
              <label key={user.id}>
                <input
                  type="checkbox"
                  checked={selectedUserIds.includes(user.id)}
                  onChange={() => toggleParticipant(user.id)}
                />
                {user.username}
              </label>
            ))}
          </fieldset>
          {isGroup && (
            <label>
              Nome do grupo
              <input
                type="text"
                value={groupName}
                onChange={(event) => setGroupName(event.target.value)}
                required
              />
            </label>
          )}
          <button type="submit" disabled={selectedUserIds.length === 0 || createMutation.isPending}>
            Criar
          </button>
        </form>
      )}
      <button type="button" onClick={handleLogout}>
        Sair
      </button>
    </main>
  )
}

export default Conversas
