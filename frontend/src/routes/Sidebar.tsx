import type { FormEvent } from 'react'
import { useCallback, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Checkbox from '@mui/material/Checkbox'
import Divider from '@mui/material/Divider'
import FormControlLabel from '@mui/material/FormControlLabel'
import IconButton from '@mui/material/IconButton'
import List from '@mui/material/List'
import ListItemButton from '@mui/material/ListItemButton'
import ListItemText from '@mui/material/ListItemText'
import Paper from '@mui/material/Paper'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import AddIcon from '@mui/icons-material/Add'
import CloseIcon from '@mui/icons-material/Close'
import GroupIcon from '@mui/icons-material/Group'
import LogoutIcon from '@mui/icons-material/Logout'
import PersonIcon from '@mui/icons-material/Person'
import { createConversation, getMe, listConversations, listUsers } from '../lib/api'
import { useAuth } from '../lib/auth/AuthContext'
import { conversationLabel } from '../lib/conversationLabel'
import { hasNewActivity, setLastSeenAt } from '../lib/lastSeen'
import { msnButtonSx } from '../lib/msnButtonStyle'
import { skyScrollbarSx } from '../lib/scrollbarStyle'
import { skyTextFieldSx } from '../lib/textFieldStyle'
import { useUserSocket } from '../lib/useUserSocket'

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
    onSuccess: (conversation) => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] })
      setIsFormOpen(false)
      setSelectedUserIds([])
      setGroupName('')
      navigate(`/conversas/${conversation.id}`)
    },
  })

  function handleLogout() {
    auth.logout()
    navigate('/')
  }

  function handleCloseForm() {
    setIsFormOpen(false)
    setSelectedUserIds([])
    setGroupName('')
  }

  function markCurrentConversationSeen() {
    if (!conversationId || !meQuery.data?.id) return
    const current = conversationsQuery.data?.find((c) => c.id === conversationId)
    if (current) {
      setLastSeenAt(meQuery.data.id, conversationId, current.last_message_at)
    }
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
        width: { xs: '100%', sm: 200, lg: 220 },
        height: '100%',
        flexShrink: 0,
        display: 'flex',
        flexDirection: 'column',
        p: 2,
        gap: 2,
        overflowY: 'auto',
        backgroundImage: 'linear-gradient(to bottom, rgb(224 242 254 / 0.9), rgb(186 230 253 / 0.5))',
        ...skyScrollbarSx,
      }}
    >
      {!isFormOpen && (
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => {
            setIsFormOpen(true)
            usersQuery.refetch()
          }}
          sx={{ ...msnButtonSx, fontSize: '0.75rem' }}
        >
          Nova conversa
        </Button>
      )}
      <Typography
        variant="h6"
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 0.75,
          fontSize: '0.75rem',
          fontWeight: 700,
          textTransform: 'uppercase',
          letterSpacing: 0.5,
          color: 'primary.dark',
        }}
      >
        <GroupIcon fontSize="small" sx={{ color: 'primary.main' }} />
        Conversas ({conversationsQuery.data?.length ?? 0})
      </Typography>
      <List
        sx={{
          flex: isFormOpen ? 'initial' : 1,
          minHeight: 0,
          overflowY: 'auto',
          ...(isFormOpen && { maxHeight: '50%' }),
          ...skyScrollbarSx,
        }}
      >
        {conversationsQuery.data?.map((conversation) => (
          <ListItemButton
            key={conversation.id}
            component={Link}
            to={`/conversas/${conversation.id}`}
            selected={conversation.id === conversationId}
            onClick={markCurrentConversationSeen}
            sx={{
              borderRadius: 1,
              mb: 0.5,
              minWidth: 0,
              borderBottom: '1px solid rgb(90 130 166 / 0.15)',
              '&.Mui-selected': {
                bgcolor: 'rgb(186 230 253 / 0.6)',
                '&:hover': { bgcolor: 'rgb(186 230 253 / 0.8)' },
              },
              '&:hover': {
                bgcolor: 'rgb(224 242 254 / 0.5)',
              },
            }}
          >
            {conversation.participant_user_ids.length > 2 ? (
              <GroupIcon aria-label="Conversa em grupo" fontSize="small" sx={{ color: 'primary.main', mr: 1, flexShrink: 0 }} />
            ) : (
              <PersonIcon aria-label="Conversa individual" fontSize="small" sx={{ color: 'primary.main', mr: 1, flexShrink: 0 }} />
            )}
            <ListItemText
              primary={conversationLabel(conversation, meQuery.data?.id, usernameById)}
              slotProps={{ primary: { noWrap: true } }}
              sx={{ minWidth: 0 }}
            />
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
      {isFormOpen && <Divider />}
      {isFormOpen && (
        <Box
          component="form"
          onSubmit={handleSubmit}
          sx={{ display: 'flex', flexDirection: 'column', gap: 1, maxHeight: '50%' }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
              Nova Conversa:
            </Typography>
            <IconButton
              aria-label="Fechar criação de conversa"
              size="small"
              onClick={handleCloseForm}
              sx={{ color: 'error.main' }}
            >
              <CloseIcon fontSize="small" />
            </IconButton>
          </Box>
          <Typography variant="subtitle2" component="legend">
            Participantes
          </Typography>
          {isGroup && (
            <TextField
              placeholder="Nome do Grupo *"
              value={groupName}
              onChange={(event) => setGroupName(event.target.value)}
              required
              size="small"
              sx={skyTextFieldSx}
            />
          )}
          <Box
            sx={{
              flex: 1,
              overflowY: 'auto',
              display: 'flex',
              flexDirection: 'column',
              minHeight: 0,
              ...skyScrollbarSx,
            }}
          >
            {otherUsers.map((user) => (
              <FormControlLabel
                key={user.id}
                sx={{ width: '100%', mx: 0, minWidth: 0 }}
                control={
                  <Checkbox
                    checked={selectedUserIds.includes(user.id)}
                    onChange={() => toggleParticipant(user.id)}
                  />
                }
                label={
                  <Typography noWrap sx={{ minWidth: 0 }}>
                    {user.username}
                  </Typography>
                }
              />
            ))}
          </Box>
          <Button
            type="submit"
            variant="contained"
            disabled={selectedUserIds.length === 0 || createMutation.isPending}
            sx={msnButtonSx}
          >
            Criar
          </Button>
        </Box>
      )}
      <Button color="error" startIcon={<LogoutIcon />} onClick={handleLogout}>
        Sair
      </Button>
    </Paper>
  )
}

export default Sidebar
