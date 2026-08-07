import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ThemeProvider } from '@mui/material/styles'
import CssBaseline from '@mui/material/CssBaseline'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './lib/auth/AuthContext'
import { theme } from './theme'
import Home from './routes/Home'
import Login from './routes/Login'
import Register from './routes/Register'
import ConversasLayout from './routes/ConversasLayout'
import ConversaEmptyState from './routes/ConversaEmptyState'
import Conversa from './routes/Conversa'
import RequireAuth from './routes/RequireAuth'

const queryClient = new QueryClient()

function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <BrowserRouter>
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />
              <Route element={<RequireAuth />}>
                <Route path="/conversas" element={<ConversasLayout />}>
                  <Route index element={<ConversaEmptyState />} />
                  <Route path=":conversationId" element={<Conversa />} />
                </Route>
              </Route>
            </Routes>
          </BrowserRouter>
        </AuthProvider>
      </QueryClientProvider>
    </ThemeProvider>
  )
}

export default App
