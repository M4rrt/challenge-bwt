import { useEffect, useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Navigate, useNavigate } from 'react-router-dom'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import CircularProgress from '@mui/material/CircularProgress'
import Typography from '@mui/material/Typography'
import LoginIcon from '@mui/icons-material/Login'
import { issueChatToken, redeemExchangeCode } from '../../lib/monolith'
import { useAuth } from '../../lib/auth/AuthContext'
import AuthLayout from '../AuthLayout/AuthLayout'
import AvatarFrame from '../AvatarFrame/AvatarFrame'

function readExchangeCodeFromFragment(): string | null {
  if (!window.location.hash) {
    return null
  }
  return new URLSearchParams(window.location.hash.slice(1)).get('code')
}

/** The code must never survive in browser history or turn into a query string. */
function clearFragment() {
  window.history.replaceState(null, '', window.location.pathname + window.location.search)
}

function SessionHandoff() {
  const auth = useAuth()
  const navigate = useNavigate()
  const [missingCode, setMissingCode] = useState(false)
  const attempted = useRef(false)

  const mutation = useMutation({
    mutationFn: async (code: string) => {
      const redemption = await redeemExchangeCode(code)
      const tokenResponse = await issueChatToken(redemption.renewal_token)
      return { redemption, tokenResponse }
    },
    onSuccess: ({ redemption, tokenResponse }) => {
      auth.login(tokenResponse.access_token, redemption.renewal_token, redemption.api_url, redemption.ws_url)
      navigate('/chats', { replace: true })
    },
  })

  useEffect(() => {
    if (auth.isAuthenticated || attempted.current) {
      return
    }
    attempted.current = true

    const code = readExchangeCodeFromFragment()
    clearFragment()

    if (!code) {
      setMissingCode(true)
      return
    }
    mutation.mutate(code)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (auth.isAuthenticated) {
    return <Navigate to="/chats" replace />
  }

  const failed = missingCode || mutation.isError

  return (
    <AuthLayout titlebarIcon={<LoginIcon fontSize="small" />} titlebarTitle="Entrando no Chat-App">
      <AvatarFrame src="/logo.png" alt="Logo" size={104} />
      {failed ? (
        <>
          <Typography variant="h6" component="h1" sx={{ textAlign: 'center' }}>
            Não foi possível entrar
          </Typography>
          <Alert severity="error">
            {missingCode
              ? 'Nenhum código de sessão foi encontrado no link. Volte ao BWT e abra o chat novamente.'
              : 'Esse link de acesso já expirou ou já foi usado. Volte ao BWT e abra o chat novamente.'}
          </Alert>
        </>
      ) : (
        <>
          <Typography variant="h6" component="h1" sx={{ textAlign: 'center' }}>
            Entrando...
          </Typography>
          <Box sx={{ display: 'flex', justifyContent: 'center' }}>
            <CircularProgress size={32} />
          </Box>
        </>
      )}
    </AuthLayout>
  )
}

export default SessionHandoff
