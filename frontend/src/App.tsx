import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './lib/auth/AuthContext'
import Home from './routes/Home'
import Login from './routes/Login'
import Register from './routes/Register'
import Conversas from './routes/Conversas'
import RequireAuth from './routes/RequireAuth'

const queryClient = new QueryClient()

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route element={<RequireAuth />}>
              <Route path="/conversas" element={<Conversas />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  )
}

export default App
