import type { FormEvent } from 'react'
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import InputAdornment from '@mui/material/InputAdornment'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import AccountCircleIcon from '@mui/icons-material/AccountCircle'
import EmailIcon from '@mui/icons-material/Email'
import KeyIcon from '@mui/icons-material/Key'
import LoginIcon from '@mui/icons-material/Login'
import { ApiError, login as loginRequest } from '../lib/api'
import { useAuth } from '../lib/auth/AuthContext'
import AuthLayout from '../components/AuthLayout'
import AvatarFrame from '../components/AvatarFrame'

function TitlebarDots() {
  return (
    <Box sx={{ display: 'flex', gap: 0.75 }} aria-hidden="true">
      <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: '#7dd3fc' }} />
      <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: '#f59e0b' }} />
    </Box>
  )
}

function Home() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const auth = useAuth()
  const navigate = useNavigate()

  const mutation = useMutation({
    mutationFn: () => loginRequest(email, password),
    onSuccess: (data) => {
      auth.login(data.access_token)
      navigate('/conversas')
    },
  })

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    mutation.mutate()
  }

  if (auth.isAuthenticated) {
    return <Navigate to="/conversas" replace />
  }

  return (
    <AuthLayout
      titlebarIcon={<AccountCircleIcon fontSize="small" />}
      titlebarTitle="Entrar no Chat-App"
      titlebarActions={<TitlebarDots />}
    >
      <AvatarFrame
        src="/logo.png"
        alt="Logo"
        size={104}
        showStatusDot
        tooltip={
          <>
            Ícones criados por IconBaandar -{' '}
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
      />
      <Typography variant="h6" component="h1" sx={{ textAlign: 'center' }}>
        Informe suas credenciais para entrar
      </Typography>
      <Box component="form" onSubmit={handleSubmit} sx={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 2 }}>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
          <Typography component="label" htmlFor="login-email" variant="body2" sx={{ fontWeight: 700 }}>
            E-mail
          </Typography>
          <TextField
            id="login-email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="voce@email.com"
            slotProps={{
              htmlInput: { required: true },
              input: {
                startAdornment: (
                  <InputAdornment position="start">
                    <EmailIcon fontSize="small" color="primary" />
                  </InputAdornment>
                ),
              },
            }}
            size="small"
            fullWidth
          />
        </Box>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
          <Typography component="label" htmlFor="login-password" variant="body2" sx={{ fontWeight: 700 }}>
            Senha
          </Typography>
          <TextField
            id="login-password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="Digite sua senha"
            slotProps={{
              htmlInput: { required: true },
              input: {
                startAdornment: (
                  <InputAdornment position="start">
                    <KeyIcon fontSize="small" color="primary" />
                  </InputAdornment>
                ),
              },
            }}
            size="small"
            fullWidth
          />
        </Box>
        <Button type="submit" variant="contained" fullWidth startIcon={<LoginIcon />} disabled={mutation.isPending}>
          Entrar
        </Button>
        {mutation.isError && (
          <Alert severity="error">
            {mutation.error instanceof ApiError && mutation.error.status === 401
              ? 'Credenciais inválidas'
              : 'Não foi possível conectar ao servidor'}
          </Alert>
        )}
      </Box>
      <Typography variant="body2">
        Ainda não possui uma conta? <Link to="/register">Cadastre-se aqui</Link>
      </Typography>
    </AuthLayout>
  )
}

export default Home
