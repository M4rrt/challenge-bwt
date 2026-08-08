import { createTheme } from '@mui/material/styles'

export const theme = createTheme({
  palette: {
    primary: {
      main: '#0284c7',
      dark: '#0c4a6e',
      light: '#7dd3fc',
    },
    secondary: {
      main: '#10b981',
    },
    warning: {
      main: '#f59e0b',
    },
    text: {
      primary: '#334155',
    },
    background: {
      default: '#eef1f6',
    },
  },
  shape: {
    borderRadius: 4,
  },
  typography: {
    h6: {
      fontWeight: 700,
      color: '#0c4a6e',
    },
    body2: {
      fontSize: '0.8rem',
    },
    button: {
      fontWeight: 700,
      textTransform: 'none',
    },
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 4,
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: ({ ownerState }) =>
          ownerState.elevation && ownerState.elevation > 0
            ? {
                borderRadius: 4,
              }
            : {},
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          fontSize: '0.8rem',
          borderRadius: 4,
        },
        input: ({ theme }) => ({
          '&:-webkit-autofill, &:-webkit-autofill:hover, &:-webkit-autofill:focus, &:-webkit-autofill:active': {
            WebkitBoxShadow: '0 0 0 1000px #fff inset',
            WebkitTextFillColor: theme.palette.text.primary,
            caretColor: theme.palette.text.primary,
            transition: 'background-color 9999s ease-in-out 0s, color 9999s ease-in-out 0s',
          },
        }),
      },
    },
  },
})
