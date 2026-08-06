import type { FormEvent } from 'react'
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { ApiError, login as loginRequest } from '../lib/api'
import { useAuth } from '../lib/auth/AuthContext'

function Login() {
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

  return (
    <main>
      <h1>Login</h1>
      <form onSubmit={handleSubmit}>
        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
        </label>
        <label>
          Senha
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </label>
        <button type="submit" disabled={mutation.isPending}>
          Entrar
        </button>
        {mutation.isError && (
          <p role="alert">
            {mutation.error instanceof ApiError && mutation.error.status === 401
              ? 'Credenciais inválidas'
              : 'Não foi possível conectar ao servidor'}
          </p>
        )}
      </form>
      <p>
        Não tem conta? <Link to="/register">Registrar</Link>
      </p>
    </main>
  )
}

export default Login
