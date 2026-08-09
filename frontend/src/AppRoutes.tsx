import { Route, Routes } from 'react-router-dom'
import Home from './components/Home/Home'
import Register from './components/Register/Register'
import ConversasLayout from './components/ConversasLayout/ConversasLayout'
import ConversaEmptyState from './components/ConversasLayout/ConversaEmptyState/ConversaEmptyState'
import Conversa from './components/ConversasLayout/Conversa/Conversa'
import RequireAuth from './components/RequireAuth/RequireAuth'
import WebhookTestPage from './components/WebhookTestPage/WebhookTestPage'

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/register" element={<Register />} />
      <Route element={<RequireAuth />}>
        <Route path="/conversas" element={<ConversasLayout />}>
          <Route index element={<ConversaEmptyState />} />
          <Route path=":conversationId" element={<Conversa />} />
        </Route>
        <Route path="/webhook" element={<WebhookTestPage />} />
      </Route>
    </Routes>
  )
}

export default AppRoutes
