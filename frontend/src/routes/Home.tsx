import type { FormEvent } from 'react'
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { ApiError, login as loginRequest } from '../lib/api'
import { useAuth } from '../lib/auth/AuthContext'
import AuthLayout from '../components/AuthLayout'

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
    <AuthLayout title="Login">
      <Box component="form" onSubmit={handleSubmit} sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
          <Typography component="label" htmlFor="login-email" variant="body2" sx={{ fontWeight: 500 }}>
            Email
          </Typography>
          <TextField
            id="login-email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            slotProps={{ htmlInput: { required: true } }}
            size="small"
            fullWidth
          />
        </Box>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
          <Typography component="label" htmlFor="login-password" variant="body2" sx={{ fontWeight: 500 }}>
            Senha
          </Typography>
          <TextField
            id="login-password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            slotProps={{ htmlInput: { required: true } }}
            size="small"
            fullWidth
          />
        </Box>
        <Button type="submit" variant="contained" fullWidth disabled={mutation.isPending}>
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
      <Typography variant="body2" sx={{ mt: 2 }}>
        Não tem conta? <Link to="/register">Registrar</Link>
      </Typography>
    </AuthLayout>
  )
}

export default Home
