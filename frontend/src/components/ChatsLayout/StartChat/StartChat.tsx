import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Checkbox from '@mui/material/Checkbox'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import IconButton from '@mui/material/IconButton'
import List from '@mui/material/List'
import ListItemButton from '@mui/material/ListItemButton'
import ListItemText from '@mui/material/ListItemText'
import TextField from '@mui/material/TextField'
import AddCommentIcon from '@mui/icons-material/AddComment'
import { ApiError } from '../../../lib/api'
import { createChat, listContacts } from '../../../lib/monolith'
import { useAuth } from '../../../lib/auth/AuthContext'
import { skyTextFieldSx } from '../textFieldStyle'
import { msnButtonSx } from '../msnButtonStyle'

const SEARCH_DEBOUNCE_MS = 300
const GENERIC_ERROR = 'Não foi possível criar o chat. Tente novamente.'

function rejectionMessage(error: unknown): string {
  if (error instanceof ApiError && error.body && typeof error.body === 'object' && 'detail' in error.body) {
    const detail = (error.body as { detail?: unknown }).detail
    if (typeof detail === 'string') return detail
  }
  return GENERIC_ERROR
}

function StartChat() {
  const auth = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const renewalToken = auth.renewalToken ?? undefined

  const [open, setOpen] = useState(false)
  const [searchInput, setSearchInput] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [name, setName] = useState('')

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(searchInput.trim()), SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [searchInput])

  const contactsQuery = useQuery({
    queryKey: ['contacts', debouncedSearch],
    queryFn: () => listContacts(renewalToken!, debouncedSearch || undefined),
    enabled: open && !!renewalToken,
  })
  const contacts = contactsQuery.data ?? []

  const needsName = selectedIds.length > 1
  const canSubmit = selectedIds.length > 0 && (!needsName || name.trim().length > 0)

  const createChatMutation = useMutation({
    mutationFn: () => createChat(renewalToken!, selectedIds, needsName ? name.trim() : undefined),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['chats'] })
      handleClose()
      navigate(`/chats/${result.chat_id}`)
    },
  })

  function toggleContact(id: string) {
    setSelectedIds((current) =>
      current.includes(id) ? current.filter((existing) => existing !== id) : [...current, id],
    )
  }

  function handleClose() {
    setOpen(false)
    setSearchInput('')
    setDebouncedSearch('')
    setSelectedIds([])
    setName('')
    createChatMutation.reset()
  }

  function handleSubmit() {
    if (!canSubmit || createChatMutation.isPending) return
    createChatMutation.mutate()
  }

  return (
    <>
      <IconButton aria-label="Iniciar novo chat" onClick={() => setOpen(true)} size="small">
        <AddCommentIcon fontSize="small" sx={{ color: 'primary.main' }} />
      </IconButton>
      <Dialog open={open} onClose={handleClose} fullWidth maxWidth="xs">
        <DialogTitle>Novo chat</DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
          {createChatMutation.isError && (
            <Alert severity="error">{rejectionMessage(createChatMutation.error)}</Alert>
          )}
          <TextField
            placeholder="Buscar contato"
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            size="small"
            sx={skyTextFieldSx}
          />
          <List dense sx={{ maxHeight: 280, overflowY: 'auto' }}>
            {contacts.map((candidate) => (
              <ListItemButton key={candidate.id} onClick={() => toggleContact(candidate.id)}>
                <Checkbox
                  edge="start"
                  disableRipple
                  tabIndex={-1}
                  checked={selectedIds.includes(candidate.id)}
                  slotProps={{ input: { 'aria-label': candidate.display_name } }}
                />
                <ListItemText primary={candidate.display_name} />
              </ListItemButton>
            ))}
          </List>
          {needsName && (
            <TextField
              label="Nome do grupo"
              value={name}
              onChange={(event) => setName(event.target.value)}
              size="small"
              required
              sx={skyTextFieldSx}
            />
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleClose}>Cancelar</Button>
          <Button
            variant="contained"
            onClick={handleSubmit}
            disabled={!canSubmit || createChatMutation.isPending}
            sx={msnButtonSx}
          >
            Iniciar chat
          </Button>
        </DialogActions>
      </Dialog>
    </>
  )
}

export default StartChat
