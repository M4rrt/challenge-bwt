import { Route, Routes } from 'react-router-dom'
import Home from './components/Home/Home'
import Register from './components/Register/Register'
import ChatsLayout from './components/ChatsLayout/ChatsLayout'
import ChatEmptyState from './components/ChatsLayout/ChatEmptyState/ChatEmptyState'
import ChatThread from './components/ChatsLayout/ChatThread/ChatThread'
import RequireAuth from './components/RequireAuth/RequireAuth'
import WebhookTestPage from './components/WebhookTestPage/WebhookTestPage'

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/register" element={<Register />} />
      <Route element={<RequireAuth />}>
        <Route path="/chats" element={<ChatsLayout />}>
          <Route index element={<ChatEmptyState />} />
          <Route path=":chatId" element={<ChatThread />} />
        </Route>
        <Route path="/webhook" element={<WebhookTestPage />} />
      </Route>
    </Routes>
  )
}

export default AppRoutes
