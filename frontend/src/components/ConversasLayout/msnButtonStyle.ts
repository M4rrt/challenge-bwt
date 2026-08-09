import type { SxProps, Theme } from '@mui/material/styles'

export const msnButtonSx: SxProps<Theme> = {
  background: 'linear-gradient(to bottom, #f0f7ff 0%, #d8e8f8 50%, #b8d4f0 100%)',
  border: '1px solid #5a82a6',
  color: '#0d3861',
  fontWeight: 600,
  textShadow: '0 1px 0 rgba(255, 255, 255, 0.8)',
  boxShadow: '0 1px 2px rgba(0, 0, 0, 0.1)',
  transition: 'all 0.15s ease',
  '&:hover': {
    background: 'linear-gradient(to bottom, #f0f7ff 0%, #d8e8f8 50%, #b8d4f0 100%)',
  },
}
