import type { FormEvent } from 'react'
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { ApiError, register as registerRequest } from '../lib/api'
import AuthLayout from '../components/AuthLayout'

function Register() {
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const navigate = useNavigate()

  const mutation = useMutation({
    mutationFn: () => registerRequest(email, username, password),
    onSuccess: () => {
      navigate('/')
    },
  })

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    mutation.mutate()
  }

  return (
    <AuthLayout title="Registrar">
      <Box component="form" onSubmit={handleSubmit} sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
          <Typography component="label" htmlFor="register-username" variant="body2" sx={{ fontWeight: 500 }}>
            Nome de usuário
          </Typography>
          <TextField
            id="register-username"
            type="text"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            slotProps={{ htmlInput: { required: true } }}
            size="small"
            fullWidth
          />
        </Box>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
          <Typography component="label" htmlFor="register-email" variant="body2" sx={{ fontWeight: 500 }}>
            Email
          </Typography>
          <TextField
            id="register-email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            slotProps={{ htmlInput: { required: true } }}
            size="small"
            fullWidth
          />
        </Box>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
          <Typography component="label" htmlFor="register-password" variant="body2" sx={{ fontWeight: 500 }}>
            Senha
          </Typography>
          <TextField
            id="register-password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            slotProps={{ htmlInput: { required: true } }}
            size="small"
            fullWidth
          />
        </Box>
        <Button type="submit" variant="contained" fullWidth disabled={mutation.isPending}>
          Criar conta
        </Button>
        {mutation.isError && (
          <Alert severity="error">
            {mutation.error instanceof ApiError && mutation.error.status === 409
              ? 'Email já cadastrado'
              : mutation.error instanceof ApiError && mutation.error.status === 422
                ? 'Senha deve ter pelo menos 8 caracteres, com maiúscula, minúscula e um número ou símbolo'
                : 'Não foi possível conectar ao servidor'}
          </Alert>
        )}
      </Box>
      <Typography variant="body2" sx={{ mt: 2 }}>
        Já tem conta? <Link to="/">Entrar</Link>
      </Typography>
    </AuthLayout>
  )
}

export default Register
