import type { SxProps, Theme } from '@mui/material/styles'

export const skyScrollbarSx: SxProps<Theme> = {
  scrollbarWidth: 'thin',
  scrollbarColor: 'rgb(186 230 253 / 1) rgb(240 249 255 / 0.6)',
  '&::-webkit-scrollbar': {
    width: 8,
  },
  '&::-webkit-scrollbar-track': {
    backgroundColor: 'rgb(240 249 255 / 0.6)',
  },
  '&::-webkit-scrollbar-thumb': {
    backgroundColor: 'rgb(186 230 253 / 1)',
    borderRadius: 4,
  },
  '&::-webkit-scrollbar-thumb:hover': {
    backgroundColor: 'rgb(125 211 252 / 1)',
  },
}
