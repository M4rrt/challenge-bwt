# 19 — The chat token is signed RS256, and the service can never mint one

**What to build:** The service stops verifying the chat token with a shared secret and starts verifying an RS256 signature against a public key it holds in configuration, selected by `kid`. After this, a compromised chat service cannot impersonate anyone: it holds no material that signs anything.

This is [ADR-0009](../../docs/adr/0009-chat-owns-token-in-rs256.md) in full. It was split out of [01](01-chat-token-replaces-own-login.md) because the signature algorithm and the claims contract are independent — [01](01-chat-token-replaces-own-login.md) settled the claims, which is what the rest of the spec is blocked on, and left the symmetric secret in place. Nothing downstream reads a signature, so this can land any time before production; it must land *before* production, because until it does the service holds a key that mints tokens it would accept.

**Blocked by:** 01.

**Blocks:** production. This is not a hardening nice-to-have — until it lands, the service holds a secret that mints tokens it would accept, and [ADR-0009](../../docs/adr/0009-chat-owns-token-in-rs256.md) is marked not-yet-implemented because of it.

**Status:** ready-for-agent

- [ ] A token signed RS256 and selected by `kid` is accepted; the public key comes from configuration so the service boots with no network
- [ ] The `aud` claim is verified and mandatory — a token with the wrong audience, and a token with no audience at all, are both rejected
- [ ] An unknown `kid`, a token signed by the wrong key, and a token declaring the `none` algorithm are each rejected
- [ ] A token with no expiry is rejected, since the short lifetime is the revocation mechanism ([ADR-0011](../../docs/adr/0011-revocation-at-the-next-token.md))
- [ ] A JWKS URL is consulted opportunistically for rotation and falls back to the last known key set; a key set fetch failing never fails a request
- [ ] The symmetric secret and its settings are gone — the service holds nothing that can sign a token it would accept
- [ ] Tests mint tokens with a test key pair whose public half is loaded into settings — the production path stays "a public key from config", unchanged

## Comments

**The claims contract does not change.** [01](01-chat-token-replaces-own-login.md)
fixed it: `sub` and `exp` as registered claims, everything else namespaced under
`https://brwinetours.com/chat`. This ticket changes only how the token is signed
and which checks run before the claims are trusted.

**Configuration shape, already decided:** one setting holding a JWKS document,
so the value read from config and the value fetched from the JWKS URL parse
through the same code path and more than one `kid` works from day one.

```
CHAT_TOKEN_JWKS='{"keys":[{"kty":"RSA","kid":"bwt-chat-2026-09","alg":"RS256","use":"sig","n":"...","e":"AQAB"}]}'
CHAT_TOKEN_JWKS_URL=https://api.brwinetours.com/.well-known/chat-jwks.json
CHAT_TOKEN_AUDIENCE=bwt-chat
CHAT_TOKEN_ISSUER=https://api.brwinetours.com
```

**The seam is already in place.** `app/core/chat_token.py` is the only thing that
turns a token into a `Caller`, and `tests/chat_tokens.py` is the only thing that
mints one. Both change; nothing that calls them does.
