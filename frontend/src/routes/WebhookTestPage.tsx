import type { FormEvent } from 'react'
import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Paper from '@mui/material/Paper'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { ApiError, type Message, getMe, sendWebhookMessage } from '../lib/api'
import { useAuth } from '../lib/auth/AuthContext'
import { signWebhookBody } from '../lib/webhookSignature'

function errorDetail(error: unknown): string {
  if (error instanceof ApiError) {
    const body = error.body
    if (body && typeof body === 'object' && 'detail' in body) {
      const detail = (body as { detail: unknown }).detail
      if (typeof detail === 'string') {
        return detail
      }
      return JSON.stringify(detail)
    }
    return `Erro ${error.status}`
  }
  if (error instanceof Error) {
    return error.message
  }
  return 'Não foi possível conectar ao servidor'
}

function WebhookTestPage() {
  const auth = useAuth()
  const token = auth.token ?? undefined
  const meQuery = useQuery({ queryKey: ['me'], queryFn: () => getMe(token!), enabled: !!token })

  const [conversationId, setConversationId] = useState('')
  const [body, setBody] = useState('')
  const [senderName, setSenderName] = useState('')

  const mutation = useMutation({
    mutationFn: async (): Promise<Message> => {
      const rawBody = JSON.stringify({
        conversation_id: conversationId,
        body,
        source_label: senderName || null,
      })
      const secret = (import.meta.env.VITE_WEBHOOK_TEST_SECRET as string | undefined) ?? ''
      if (!secret) {
        throw new Error('VITE_WEBHOOK_TEST_SECRET não configurado')
      }
      const signature = await signWebhookBody(secret, rawBody)
      return sendWebhookMessage(rawBody, signature)
    },
  })

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    mutation.mutate()
  }

  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        justifyContent: 'center',
        bgcolor: 'background.default',
        px: { xs: 2, sm: 8 },
        py: 6,
      }}
    >
      <Paper
        elevation={2}
        sx={{ width: '100%', maxWidth: 480, p: 4, display: 'flex', flexDirection: 'column', gap: 2 }}
      >
        <Typography variant="h6" component="h1">
          Teste de WebHook
        </Typography>
        <Typography variant="body2">{meQuery.data?.username}</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ fontStyle: 'italic' }}>
          essa é apenas uma pagina para teste do WebHook
        </Typography>
        <Box component="form" onSubmit={handleSubmit} sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
            <Typography component="label" htmlFor="webhook-conversation-id" variant="body2" sx={{ fontWeight: 500 }}>
              Conversation ID
            </Typography>
            <TextField
              id="webhook-conversation-id"
              value={conversationId}
              onChange={(event) => setConversationId(event.target.value)}
              slotProps={{ htmlInput: { required: true } }}
              size="small"
              fullWidth
            />
          </Box>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
            <Typography component="label" htmlFor="webhook-body" variant="body2" sx={{ fontWeight: 500 }}>
              Mensagem
            </Typography>
            <TextField
              id="webhook-body"
              value={body}
              onChange={(event) => setBody(event.target.value)}
              slotProps={{ htmlInput: { required: true } }}
              size="small"
              fullWidth
              multiline
              minRows={3}
            />
          </Box>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
            <Typography component="label" htmlFor="webhook-sender-name" variant="body2" sx={{ fontWeight: 500 }}>
              Nome do remetente
            </Typography>
            <TextField
              id="webhook-sender-name"
              value={senderName}
              onChange={(event) => setSenderName(event.target.value)}
              size="small"
              fullWidth
            />
          </Box>
          <Button type="submit" variant="contained" disabled={mutation.isPending}>
            Enviar
          </Button>
        </Box>
        {mutation.isSuccess && (
          <Alert severity="success">
            <Box component="dl" sx={{ m: 0, display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '2px 8px' }}>
              <Typography component="dt" variant="body2" sx={{ fontWeight: 500 }}>id</Typography>
              <Typography component="dd" variant="body2" sx={{ m: 0 }}>{mutation.data.id}</Typography>
              <Typography component="dt" variant="body2" sx={{ fontWeight: 500 }}>conversation_id</Typography>
              <Typography component="dd" variant="body2" sx={{ m: 0 }}>{mutation.data.conversation_id}</Typography>
              <Typography component="dt" variant="body2" sx={{ fontWeight: 500 }}>sender_type</Typography>
              <Typography component="dd" variant="body2" sx={{ m: 0 }}>{mutation.data.sender_type}</Typography>
              <Typography component="dt" variant="body2" sx={{ fontWeight: 500 }}>source_label</Typography>
              <Typography component="dd" variant="body2" sx={{ m: 0 }}>{mutation.data.source_label ?? '—'}</Typography>
              <Typography component="dt" variant="body2" sx={{ fontWeight: 500 }}>body</Typography>
              <Typography component="dd" variant="body2" sx={{ m: 0 }}>{mutation.data.body}</Typography>
              <Typography component="dt" variant="body2" sx={{ fontWeight: 500 }}>created_at</Typography>
              <Typography component="dd" variant="body2" sx={{ m: 0 }}>{mutation.data.created_at}</Typography>
            </Box>
          </Alert>
        )}
        {mutation.isError && <Alert severity="error">{errorDetail(mutation.error)}</Alert>}
      </Paper>
    </Box>
  )
}

export default WebhookTestPage
