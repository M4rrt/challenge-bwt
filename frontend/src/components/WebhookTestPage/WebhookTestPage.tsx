import type { FormEvent } from 'react'
import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Link as RouterLink } from 'react-router-dom'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import InputAdornment from '@mui/material/InputAdornment'
import Link from '@mui/material/Link'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import BadgeIcon from '@mui/icons-material/Badge'
import ChatBubbleOutlinedIcon from '@mui/icons-material/ChatBubbleOutlined'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import SendIcon from '@mui/icons-material/Send'
import SmartToyIcon from '@mui/icons-material/SmartToy'
import TagIcon from '@mui/icons-material/Tag'
import { ApiError, type Message, getMe, sendWebhookMessage } from '../../lib/api'
import { useAuth } from '../../lib/auth/AuthContext'
import { signWebhookBody } from './webhookSignature'
import AvatarFrame from '../AvatarFrame/AvatarFrame'
import WindowChrome from '../WindowChrome/WindowChrome'

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
        flexDirection: 'column',
        alignItems: 'center',
        bgcolor: '#a4c2e6',
        px: { xs: 4, sm: 6, md: 12 },
        py: 6,
        gap: 3,
      }}
    >
      <WindowChrome
        icon={<SmartToyIcon fontSize="small" />}
        title="Painel de Integração e Teste de WebHook"
        maxWidth="100%"
        bodySx={{ alignItems: 'flex-start' }}
        actions={
          <Button
            component={RouterLink}
            to="/conversas"
            size="small"
            startIcon={<ArrowBackIcon fontSize="small" />}
            sx={{ color: '#fff' }}
          >
            Voltar às Conversas
          </Button>
        }
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <AvatarFrame src="/logo.png" alt="Avatar do usuário conectado" size={40} />
          <Typography variant="body2" sx={{ fontWeight: 700 }}>
            Usuário Conectado: {meQuery.data?.username}
          </Typography>
          <Chip label="Ativo" color="success" size="small" />
        </Box>
        <Box
          sx={{
            display: 'flex',
            gap: 1,
            alignItems: 'flex-start',
            p: 1.5,
            width: '100%',
            borderRadius: 0.5,
            bgcolor: 'rgb(254 243 199 / 0.6)',
            border: '1px solid',
            borderColor: 'warning.light',
          }}
        >
          <InfoOutlinedIcon color="warning" fontSize="small" />
          <Typography variant="body2" component="div" color="text.secondary">
            <Typography component="span" sx={{ fontWeight: 700 }}>
              Atenção:{' '}
            </Typography>
            <Typography component="span" variant="body2" color="text.secondary">
              essa é apenas uma pagina para teste do WebHook
            </Typography>
          </Typography>
        </Box>
        <Box
          component="form"
          onSubmit={handleSubmit}
          sx={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 2 }}
        >
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
            <Typography component="label" htmlFor="webhook-conversation-id" variant="body2" sx={{ fontWeight: 700 }}>
              Conversation ID
            </Typography>
            <TextField
              id="webhook-conversation-id"
              value={conversationId}
              onChange={(event) => setConversationId(event.target.value)}
              placeholder="ex: 3f29a1b2-conversa"
              slotProps={{
                htmlInput: { required: true },
                input: {
                  startAdornment: (
                    <InputAdornment position="start">
                      <TagIcon fontSize="small" color="primary" />
                    </InputAdornment>
                  ),
                },
              }}
              size="small"
              fullWidth
            />
          </Box>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
            <Typography component="label" htmlFor="webhook-body" variant="body2" sx={{ fontWeight: 700 }}>
              Mensagem
            </Typography>
            <TextField
              id="webhook-body"
              value={body}
              onChange={(event) => setBody(event.target.value)}
              placeholder="Digite a mensagem de teste..."
              slotProps={{
                htmlInput: { required: true },
                input: {
                  startAdornment: (
                    <InputAdornment position="start" sx={{ alignSelf: 'flex-start', mt: 1 }}>
                      <ChatBubbleOutlinedIcon fontSize="small" color="primary" />
                    </InputAdornment>
                  ),
                },
              }}
              size="small"
              fullWidth
              multiline
              minRows={3}
            />
          </Box>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
            <Typography component="label" htmlFor="webhook-sender-name" variant="body2" sx={{ fontWeight: 700 }}>
              Nome do remetente
            </Typography>
            <TextField
              id="webhook-sender-name"
              value={senderName}
              onChange={(event) => setSenderName(event.target.value)}
              placeholder="ex: CRM, Bot, Suporte"
              slotProps={{
                input: {
                  startAdornment: (
                    <InputAdornment position="start">
                      <BadgeIcon fontSize="small" color="primary" />
                    </InputAdornment>
                  ),
                },
              }}
              size="small"
              fullWidth
            />
          </Box>
          <Button type="submit" variant="contained" startIcon={<SendIcon />} disabled={mutation.isPending}>
            Enviar WebHook de Teste
          </Button>
        </Box>
        {mutation.isSuccess && (
          <Alert severity="success" sx={{ width: '100%' }}>
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
        {mutation.isError && (
          <Alert severity="error" sx={{ width: '100%' }}>
            {errorDetail(mutation.error)}
          </Alert>
        )}
      </WindowChrome>
      <Link
        component={RouterLink}
        to="/conversas"
        underline="none"
        sx={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 0.75,
          px: 2.5,
          py: 0.75,
          borderRadius: 1,
          bgcolor: '#0c3a66',
          color: '#fff',
          fontSize: '0.8rem',
          fontWeight: 700,
          boxShadow: '0 1px 3px rgba(0, 0, 0, 0.2)',
          transition: 'transform 0.15s ease, background-color 0.15s ease',
          '&:hover': {
            bgcolor: '#0a2f54',
            transform: 'scale(1.03)',
          },
        }}
      >
        <ArrowBackIcon fontSize="inherit" />
        Voltar às Conversas
      </Link>
    </Box>
  )
}

export default WebhookTestPage
