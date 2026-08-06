import type { FormEvent } from 'react'
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { ApiError, register as registerRequest } from '../lib/api'

function Register() {
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const navigate = useNavigate()

  const mutation = useMutation({
    mutationFn: () => registerRequest(email, username, password),
    onSuccess: () => {
      navigate('/login')
    },
  })

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    mutation.mutate()
  }

  return (
    <main>
      <h1>Registrar</h1>
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
          Nome de usuário
          <input
            type="text"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
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
          Criar conta
        </button>
        {mutation.isError && (
          <p role="alert">
            {mutation.error instanceof ApiError && mutation.error.status === 409
              ? 'Email já cadastrado'
              : mutation.error instanceof ApiError && mutation.error.status === 422
                ? 'Senha deve ter pelo menos 8 caracteres, com maiúscula, minúscula e um número ou símbolo'
                : 'Não foi possível conectar ao servidor'}
          </p>
        )}
      </form>
      <p>
        Já tem conta? <Link to="/login">Entrar</Link>
      </p>
    </main>
  )
}

export default Register
