import { Route, Routes } from 'react-router-dom'
import SessionHandoff from './components/SessionHandoff/SessionHandoff'
import ChatsLayout from './components/ChatsLayout/ChatsLayout'
import ChatEmptyState from './components/ChatsLayout/ChatEmptyState/ChatEmptyState'
import ChatThread from './components/ChatsLayout/ChatThread/ChatThread'
import RequireAuth from './components/RequireAuth/RequireAuth'
import WebhookTestPage from './components/WebhookTestPage/WebhookTestPage'

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<SessionHandoff />} />
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
