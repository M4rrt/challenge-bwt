import Box from '@mui/material/Box'
import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'

function ConversasLayout() {
  return (
    <Box sx={{ display: 'flex', height: '100vh', gap: 2, p: 2, bgcolor: 'background.default' }}>
      <Box sx={{ flex: 1, display: 'flex' }}>
        <Outlet />
      </Box>
      <Sidebar />
    </Box>
  )
}

export default ConversasLayout
