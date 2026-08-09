import type { ReactNode } from 'react'
import Box from '@mui/material/Box'
import Paper from '@mui/material/Paper'
import Typography from '@mui/material/Typography'
import type { SxProps, Theme } from '@mui/material/styles'

interface WindowChromeProps {
  icon: ReactNode
  title: string
  actions?: ReactNode
  children: ReactNode
  maxWidth?: number | string
  bodySx?: SxProps<Theme>
}

function WindowChrome({ icon, title, actions, children, maxWidth = 420, bodySx }: WindowChromeProps) {
  return (
    <Paper
      elevation={4}
      sx={{
        width: '100%',
        maxWidth,
        borderRadius: 1,
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 1,
          px: 2,
          py: 1,
          background: 'linear-gradient(to right, #0c4a6e, #0284c7)',
          color: '#fff',
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: 0 }}>
          <Box sx={{ display: 'flex', color: '#e0f2fe' }}>{icon}</Box>
          <Typography sx={{ fontWeight: 700, fontSize: '0.8rem' }} noWrap>
            {title}
          </Typography>
        </Box>
        {actions}
      </Box>
      <Box sx={{ p: 3, display: 'flex', flexDirection: 'column', gap: 2, ...bodySx }}>{children}</Box>
    </Paper>
  )
}

export default WindowChrome
