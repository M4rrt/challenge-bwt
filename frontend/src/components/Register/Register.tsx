import type { FormEvent } from 'react'
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import InputAdornment from '@mui/material/InputAdornment'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import EmailIcon from '@mui/icons-material/Email'
import LockIcon from '@mui/icons-material/Lock'
import PersonAddIcon from '@mui/icons-material/PersonAdd'
import PersonIcon from '@mui/icons-material/Person'
import { ApiError, register as registerRequest } from '../../lib/api'
import AuthLayout from '../AuthLayout/AuthLayout'
import AvatarFrame from '../AvatarFrame/AvatarFrame'

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
    <AuthLayout titlebarIcon={<PersonAddIcon fontSize="small" />} titlebarTitle="Criar nova conta no Chat-App">
      <AvatarFrame
        src="/logo.png"
        alt="Logo"
        size={72}
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
        Cadastro de Novo Usuário
      </Typography>
      <Box component="form" onSubmit={handleSubmit} sx={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 2 }}>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
          <Typography component="label" htmlFor="register-username" variant="body2" sx={{ fontWeight: 700 }}>
            Nome de Usuário (Nick do Chat-App)
          </Typography>
          <TextField
            id="register-username"
            type="text"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            placeholder="xX_Sonhadora2007_Xx"
            slotProps={{
              htmlInput: { required: true },
              input: {
                startAdornment: (
                  <InputAdornment position="start">
                    <PersonIcon fontSize="small" color="primary" />
                  </InputAdornment>
                ),
              },
            }}
            size="small"
            fullWidth
          />
        </Box>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
          <Typography component="label" htmlFor="register-email" variant="body2" sx={{ fontWeight: 700 }}>
            E-mail
          </Typography>
          <TextField
            id="register-email"
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
          <Typography component="label" htmlFor="register-password" variant="body2" sx={{ fontWeight: 700 }}>
            Senha
          </Typography>
          <TextField
            id="register-password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="Crie uma senha segura"
            slotProps={{
              htmlInput: { required: true },
              input: {
                startAdornment: (
                  <InputAdornment position="start">
                    <LockIcon fontSize="small" color="primary" />
                  </InputAdornment>
                ),
              },
            }}
            size="small"
            fullWidth
          />
        </Box>
        <Button type="submit" variant="contained" fullWidth startIcon={<CheckCircleIcon />} disabled={mutation.isPending}>
          Concluir Cadastro
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
      <Typography variant="body2">
        Já possui uma conta no Chat-App? <Link to="/">Ir para Tela de Login</Link>
      </Typography>
    </AuthLayout>
  )
}

export default Register
