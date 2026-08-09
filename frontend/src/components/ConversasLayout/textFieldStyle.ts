import type { SxProps, Theme } from '@mui/material/styles'

export const skyTextFieldSx: SxProps<Theme> = {
  bgcolor: 'background.paper',
  borderRadius: 1,
  '& .MuiOutlinedInput-root:hover .MuiOutlinedInput-notchedOutline': {
    borderColor: 'rgb(125 211 252 / var(--tw-border-opacity, 1))',
  },
  '& .MuiOutlinedInput-root.Mui-focused .MuiOutlinedInput-notchedOutline': {
    borderColor: 'rgb(125 211 252 / var(--tw-border-opacity, 1))',
  },
}
