import type { UIEvent } from 'react'
import { useCallback, useEffect, useState } from 'react'
import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import List from '@mui/material/List'
import ListItemButton from '@mui/material/ListItemButton'
import ListItemText from '@mui/material/ListItemText'
import Paper from '@mui/material/Paper'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import GroupIcon from '@mui/icons-material/Group'
import LogoutIcon from '@mui/icons-material/Logout'
import PersonIcon from '@mui/icons-material/Person'
import SearchIcon from '@mui/icons-material/Search'
import { getMe, listChats } from '../../../lib/api'
import { useAuth } from '../../../lib/auth/AuthContext'
import { chatLabel } from '../chatLabel'
import { skyScrollbarSx } from '../scrollbarStyle'
import { skyTextFieldSx } from '../textFieldStyle'
import { useUserSocket } from './useUserSocket'

const SEARCH_DEBOUNCE_MS = 300
const SCROLL_BOTTOM_THRESHOLD_PX = 40

function Sidebar() {
  const auth = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { chatId } = useParams<{ chatId: string }>()
  const token = auth.token ?? undefined

  const [searchInput, setSearchInput] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(searchInput.trim()), SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [searchInput])

  const meQuery = useQuery({ queryKey: ['me'], queryFn: () => getMe(token!), enabled: !!token })
  const chatsQuery = useInfiniteQuery({
    queryKey: ['chats', debouncedSearch],
    queryFn: ({ pageParam }: { pageParam: string | undefined }) =>
      listChats(token!, { search: debouncedSearch || undefined, before: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: !!token,
  })

  const chats = chatsQuery.data?.pages.flatMap((page) => page.chats) ?? []

  const invalidateChats = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['chats'] })
  }, [queryClient])

  function handleUnauthenticated() {
    auth.logout()
    navigate('/')
  }

  useUserSocket({
    token,
    onMessage: invalidateChats,
    onReconnect: invalidateChats,
    onUnauthenticated: handleUnauthenticated,
  })

  function handleLogout() {
    auth.logout()
    navigate('/')
  }

  function handleScroll(event: UIEvent<HTMLUListElement>) {
    const el = event.currentTarget
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < SCROLL_BOTTOM_THRESHOLD_PX
    if (nearBottom && chatsQuery.hasNextPage && !chatsQuery.isFetchingNextPage) {
      chatsQuery.fetchNextPage()
    }
  }

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
      <TextField
        placeholder="Buscar por nome"
        value={searchInput}
        onChange={(event) => setSearchInput(event.target.value)}
        size="small"
        sx={skyTextFieldSx}
        slotProps={{
          input: { startAdornment: <SearchIcon fontSize="small" sx={{ mr: 0.75, color: 'primary.main' }} /> },
        }}
      />
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
        Chats ({chats.length})
      </Typography>
      <List
        onScroll={handleScroll}
        sx={{ flex: 1, minHeight: 0, overflowY: 'auto', ...skyScrollbarSx }}
      >
        {chats.map((chat) => (
          <ListItemButton
            key={chat.id}
            component={Link}
            to={`/chats/${chat.id}`}
            selected={chat.id === chatId}
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
            {chat.participant_user_ids.length > 2 ? (
              <GroupIcon aria-label="Chat em grupo" fontSize="small" sx={{ color: 'primary.main', mr: 1, flexShrink: 0 }} />
            ) : (
              <PersonIcon aria-label="Chat individual" fontSize="small" sx={{ color: 'primary.main', mr: 1, flexShrink: 0 }} />
            )}
            <ListItemText
              primary={chatLabel(chat, meQuery.data?.id)}
              secondary={chat.last_message?.body || 'Nenhuma mensagem ainda'}
              slotProps={{ primary: { noWrap: true }, secondary: { noWrap: true } }}
              sx={{ minWidth: 0 }}
            />
            {chat.id !== chatId && chat.unread_count > 0 && (
              <Chip
                label={chat.unread_count}
                size="small"
                color="primary"
                sx={{ ml: 1, height: 20, flexShrink: 0 }}
              />
            )}
          </ListItemButton>
        ))}
      </List>
      <Button color="error" startIcon={<LogoutIcon />} onClick={handleLogout}>
        Sair
      </Button>
    </Paper>
  )
}

export default Sidebar
