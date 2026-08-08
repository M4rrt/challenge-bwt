import { describe, expect, it } from 'vitest'
import { signWebhookBody } from './webhookSignature'

describe('signWebhookBody', () => {
  it('returns the hex HMAC-SHA256 digest of the body keyed with the secret', async () => {
    // Expected value computed independently with Python's
    // hmac.new(b'test-secret', body, hashlib.sha256).hexdigest() to verify
    // parity with the backend's verify_webhook_signature.
    const secret = 'test-secret'
    const body = JSON.stringify({ conversation_id: 'conv-1', body: 'oi', source_label: 'crm' })
    const expected = '3107234a4352aaea341c29ccd7ab7dc1c55a64a8c622880eced3ac5772ecc1d6'

    const result = await signWebhookBody(secret, body)

    expect(result).toBe(expected)
  })

  it('produces different digests for different bodies', async () => {
    const secret = 'test-secret'
    const first = await signWebhookBody(secret, 'body-a')
    const second = await signWebhookBody(secret, 'body-b')

    expect(first).not.toBe(second)
  })
})
