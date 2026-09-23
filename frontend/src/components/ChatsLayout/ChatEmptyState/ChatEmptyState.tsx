import Paper from '@mui/material/Paper'
import Typography from '@mui/material/Typography'

function ChatEmptyState() {
  return (
    <Paper
      elevation={0}
      sx={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
    >
      <Typography color="text.secondary">Selecione um chat para começar</Typography>
    </Paper>
  )
}

export default ChatEmptyState
