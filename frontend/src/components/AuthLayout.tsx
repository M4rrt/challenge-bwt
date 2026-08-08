import type { ReactNode } from 'react'
import Box from '@mui/material/Box'
import Paper from '@mui/material/Paper'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'

interface AuthLayoutProps {
  title: string
  children: ReactNode
}

function AuthLayout({ title, children }: AuthLayoutProps) {
  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        bgcolor: 'background.default',
        p: 2,
      }}
    >
      <Paper
        elevation={2}
        sx={{
          width: '100%',
          maxWidth: 380,
          p: 4,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 2,
        }}
      >
        <Tooltip
          title={
            <>
              Msn icons created by IconBaandar -{' '}
              <a
                href="https://www.flaticon.com/free-icons/msn"
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: 'inherit' }}
              >
                Flaticon
              </a>
            </>
          }
        >
          <Box
            component="img"
            src="/logo.png"
            alt="Logo"
            sx={{
              width: 112,
              height: 112,
              objectFit: 'contain',
              borderRadius: 2,
              border: '1px solid',
              borderColor: 'divider',
              p: 1,
              bgcolor: '#fff',
            }}
          />
        </Tooltip>
        <Typography variant="h6" component="h1">
          {title}
        </Typography>
        <Box sx={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 2 }}>{children}</Box>
      </Paper>
    </Box>
  )
}

export default AuthLayout
