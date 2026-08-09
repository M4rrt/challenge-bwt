import type { ReactNode } from 'react'
import Box from '@mui/material/Box'
import Tooltip from '@mui/material/Tooltip'

interface AvatarFrameProps {
  src: string
  alt: string
  size?: number
  showStatusDot?: boolean
  tooltip?: ReactNode
}

function AvatarFrame({ src, alt, size = 96, showStatusDot = false, tooltip }: AvatarFrameProps) {
  const image = (
    <Box
      component="img"
      src={src}
      alt={alt}
      sx={{
        width: size,
        height: size,
        objectFit: 'contain',
        borderRadius: '50%',
        border: '3px solid',
        borderColor: 'primary.main',
        bgcolor: '#fff',
        p: 1,
      }}
    />
  )

  return (
    <Box sx={{ position: 'relative', display: 'inline-flex' }}>
      {tooltip ? <Tooltip title={tooltip}>{image}</Tooltip> : image}
      {showStatusDot && (
        <Box
          aria-label="Status: online"
          sx={{
            position: 'absolute',
            bottom: 0,
            right: 0,
            width: size * 0.26,
            height: size * 0.26,
            borderRadius: '50%',
            bgcolor: 'success.main',
            border: '2px solid #fff',
          }}
        />
      )}
    </Box>
  )
}

export default AvatarFrame
