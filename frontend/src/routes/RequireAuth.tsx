import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../lib/auth/AuthContext'

function RequireAuth() {
  const { isAuthenticated } = useAuth()

  if (!isAuthenticated) {
    return <Navigate to="/" replace />
  }

  return <Outlet />
}

export default RequireAuth
