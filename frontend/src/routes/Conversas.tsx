import { useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth/AuthContext'

function Conversas() {
  const auth = useAuth()
  const navigate = useNavigate()

  function handleLogout() {
    auth.logout()
    navigate('/login')
  }

  return (
    <main>
      <h1>Conversas</h1>
      <p>Placeholder — lista de conversas real chega no ticket 09.</p>
      <button type="button" onClick={handleLogout}>
        Sair
      </button>
    </main>
  )
}

export default Conversas
