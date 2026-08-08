import type { FormEvent } from 'react'
import { useCallback, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Checkbox from '@mui/material/Checkbox'
import FormControlLabel from '@mui/material/FormControlLabel'
import List from '@mui/material/List'
import ListItemButton from '@mui/material/ListItemButton'
import ListItemText from '@mui/material/ListItemText'
import Paper from '@mui/material/Paper'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import {
  type Conversation,
  createConversation,
  getMe,
  listConversations,
  listUsers,
} from '../lib/api'
import { useAuth } from '../lib/auth/AuthContext'
import { hasNewActivity } from '../lib/lastSeen'
import { useUserSocket } from '../lib/useUserSocket'

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

function Sidebar() {
  const auth = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { conversationId } = useParams<{ conversationId: string }>()
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

  const handleUserSocketMessage = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['conversations'] })
  }, [queryClient])

  useUserSocket({ token, onMessage: handleUserSocketMessage })

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
    <Paper
      elevation={0}
      sx={{
        width: 320,
        display: 'flex',
        flexDirection: 'column',
        p: 2,
        gap: 2,
        overflowY: 'auto',
      }}
    >
      <Typography variant="h6">Conversas</Typography>
      <List sx={{ flex: isFormOpen ? 'initial' : 1 }}>
        {conversationsQuery.data?.map((conversation) => (
          <ListItemButton
            key={conversation.id}
            component={Link}
            to={`/conversas/${conversation.id}`}
            selected={conversation.id === conversationId}
          >
            <ListItemText primary={conversationLabel(conversation, meQuery.data?.id, usernameById)} />
            {conversation.last_message_at}
            {conversation.id !== conversationId &&
              meQuery.data?.id &&
              hasNewActivity(meQuery.data.id, conversation) && (
                <Box
                  component="span"
                  aria-label="Nova atividade"
                  sx={{
                    width: 8,
                    height: 8,
                    borderRadius: '50%',
                    bgcolor: 'primary.main',
                    display: 'inline-block',
                    ml: 1,
                  }}
                />
              )}
          </ListItemButton>
        ))}
      </List>
      {!isFormOpen && (
        <Button
          variant="contained"
          onClick={() => {
            setIsFormOpen(true)
            usersQuery.refetch()
          }}
        >
          Nova conversa
        </Button>
      )}
      {isFormOpen && (
        <Box component="form" onSubmit={handleSubmit} sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          <Typography variant="subtitle2" component="legend">
            Participantes
          </Typography>
          {otherUsers.map((user) => (
            <FormControlLabel
              key={user.id}
              control={
                <Checkbox
                  checked={selectedUserIds.includes(user.id)}
                  onChange={() => toggleParticipant(user.id)}
                />
              }
              label={user.username}
            />
          ))}
          {isGroup && (
            <TextField
              label="Nome do grupo"
              value={groupName}
              onChange={(event) => setGroupName(event.target.value)}
              required
              size="small"
            />
          )}
          <Button
            type="submit"
            variant="contained"
            disabled={selectedUserIds.length === 0 || createMutation.isPending}
          >
            Criar
          </Button>
        </Box>
      )}
      <Button onClick={handleLogout}>Sair</Button>
    </Paper>
  )
}

export default Sidebar
