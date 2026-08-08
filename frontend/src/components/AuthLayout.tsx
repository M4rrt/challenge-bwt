import type { ReactNode } from 'react'
import Box from '@mui/material/Box'
import WindowChrome from './WindowChrome'

interface AuthLayoutProps {
  titlebarIcon: ReactNode
  titlebarTitle: string
  titlebarActions?: ReactNode
  children: ReactNode
}

function AuthLayout({ titlebarIcon, titlebarTitle, titlebarActions, children }: AuthLayoutProps) {
  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        bgcolor: '#a4c2e6',
        p: 2,
      }}
    >
      <WindowChrome
        icon={titlebarIcon}
        title={titlebarTitle}
        actions={titlebarActions}
        bodySx={{ alignItems: 'center' }}
      >
        {children}
      </WindowChrome>
    </Box>
  )
}

export default AuthLayout
