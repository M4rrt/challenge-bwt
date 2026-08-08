import { useEffect, useState } from 'react'
import Box from '@mui/material/Box'
import Drawer from '@mui/material/Drawer'
import IconButton from '@mui/material/IconButton'
import Link from '@mui/material/Link'
import ArrowForwardIcon from '@mui/icons-material/ArrowForward'
import MenuIcon from '@mui/icons-material/Menu'
import { useTheme } from '@mui/material/styles'
import useMediaQuery from '@mui/material/useMediaQuery'
import { Link as RouterLink, Outlet, useParams } from 'react-router-dom'
import Sidebar from './Sidebar'

function ConversasLayout() {
  const theme = useTheme()
  const isDesktop = useMediaQuery(theme.breakpoints.up('sm'))
  const [drawerOpen, setDrawerOpen] = useState(false)
  const { conversationId } = useParams<{ conversationId: string }>()

  useEffect(() => {
    setDrawerOpen(false)
  }, [conversationId])

  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        px: { xs: 4, sm: 6, md: 12 },
        py: 2,
        gap: 1,
        bgcolor: '#a4c2e6',
      }}
    >
      <Box sx={{ flex: 1, display: 'flex', gap: 2, minHeight: 0 }}>
        <Box sx={{ flex: 1, display: 'flex', position: 'relative' }}>
          {!isDesktop && (
            <IconButton
              aria-label="Abrir lista de conversas"
              onClick={() => setDrawerOpen(true)}
              sx={{
                position: 'absolute',
                top: 12,
                right: 16,
                zIndex: 1,
                bgcolor: 'rgb(255 255 255 / 0.7)',
                '&:hover': { bgcolor: 'rgb(255 255 255 / 0.9)' },
              }}
            >
              <MenuIcon />
            </IconButton>
          )}
          <Outlet />
        </Box>
        {isDesktop ? (
          <Sidebar />
        ) : (
          <Drawer
            anchor="right"
            open={drawerOpen}
            onClose={() => setDrawerOpen(false)}
            slotProps={{
              paper: {
                sx: {
                  width: 280,
                  backgroundImage:
                    'linear-gradient(to bottom, rgb(224 242 254 / 0.9), rgb(186 230 253 / 0.5))',
                },
              },
            }}
          >
            <Sidebar />
          </Drawer>
        )}
      </Box>
      <Box component="footer" sx={{ textAlign: 'center', py: 1 }}>
        <Link
          component={RouterLink}
          to="/webhook"
          underline="none"
          sx={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 0.75,
            px: 2.5,
            py: 0.75,
            borderRadius: 999,
            bgcolor: '#0c3a66',
            color: '#fff',
            fontSize: '0.8rem',
            fontWeight: 600,
            boxShadow: '0 1px 3px rgba(0, 0, 0, 0.2)',
            transition: 'transform 0.15s ease, background-color 0.15s ease',
            '&:hover': {
              bgcolor: '#0a2f54',
              transform: 'scale(1.03)',
            },
          }}
        >
          Usar webHook
          <ArrowForwardIcon fontSize="inherit" />
        </Link>
      </Box>
    </Box>
  )
}

export default ConversasLayout
