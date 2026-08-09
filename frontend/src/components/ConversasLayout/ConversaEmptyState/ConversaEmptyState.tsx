import Paper from '@mui/material/Paper'
import Typography from '@mui/material/Typography'

function ConversaEmptyState() {
  return (
    <Paper
      elevation={0}
      sx={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
    >
      <Typography color="text.secondary">Selecione uma conversa para começar</Typography>
    </Paper>
  )
}

export default ConversaEmptyState
