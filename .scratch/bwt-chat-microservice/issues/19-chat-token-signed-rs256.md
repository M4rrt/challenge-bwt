# 19 — The chat token is signed RS256, and the service can never mint one

**What to build:** The service stops verifying the chat token with a shared secret and starts verifying an RS256 signature against a public key it holds in configuration, selected by `kid`. After this, a compromised chat service cannot impersonate anyone: it holds no material that signs anything.

This is [ADR-0009](../../docs/adr/0009-chat-owns-token-in-rs256.md) in full. It was split out of [01](01-chat-token-replaces-own-login.md) because the signature algorithm and the claims contract are independent — [01](01-chat-token-replaces-own-login.md) settled the claims, which is what the rest of the spec is blocked on, and left the symmetric secret in place. Nothing downstream reads a signature, so this can land any time before production; it must land *before* production, because until it does the service holds a key that mints tokens it would accept.

**Blocked by:** 01.

**Blocks:** production. This is not a hardening nice-to-have — until it lands, the service holds a secret that mints tokens it would accept, and [ADR-0009](../../docs/adr/0009-chat-owns-token-in-rs256.md) is marked not-yet-implemented because of it.

**Status:** done

- [x] A token signed RS256 and selected by `kid` is accepted; the public key comes from configuration so the service boots with no network
- [x] The `aud` claim is verified and mandatory — a token with the wrong audience, and a token with no audience at all, are both rejected
- [x] An unknown `kid`, a token signed by the wrong key, and a token declaring the `none` algorithm are each rejected
- [x] A token with no expiry is rejected, since the short lifetime is the revocation mechanism ([ADR-0011](../../docs/adr/0011-revocation-at-the-next-token.md))
- [x] A JWKS URL is consulted opportunistically for rotation and falls back to the last known key set; a key set fetch failing never fails a request
- [x] The symmetric secret and its settings are gone — the service holds nothing that can sign a token it would accept
- [x] Tests mint tokens with a test key pair whose public half is loaded into settings — the production path stays "a public key from config", unchanged

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

## Comments

Landed. `verify_chat_token` reads the unverified header, rejects anything
whose `alg` isn't `RS256` before any key lookup (closes the classic
algorithm-confusion path), looks up the key by `kid` in an active keyset
seeded from `CHAT_TOKEN_JWKS`, and decodes with `audience=` +
`options={"require_aud": True}` — worth flagging: passing `audience=` to
`python-jose`'s `jwt.decode` alone does *not* make `aud` mandatory in this
version (it only validates `aud` if the token happens to carry one), so the
`require_aud` option is what actually makes a missing audience a rejection,
not just a wrong one. A wrong-key signature and an unknown `kid` are both
rejected (unknown `kid` short-circuits before decode ever runs; wrong-key
resolves to a real key dict and fails signature verification).

`app/services/chat_token_keys.py` is new: a lifespan-managed background loop
(same shape as `run_subscriber`) that polls `CHAT_TOKEN_JWKS_URL`
opportunistically and replaces the active keyset wholesale on a successful
fetch — a failed fetch (network, non-200, malformed body) is logged and
leaves the previous keyset untouched, and no URL configured makes the loop a
permanent no-op. `httpx` moved from the `dev` dependency group to
`[project] dependencies` since it's now used by production code, not only by
tests. `tests/test_composition_commands.py`'s structural
"no module holds an HTTP client" check gained a named exemption for this one
file, since ADR-0010 only forbids an HTTP client reachable from a request —
this one runs only in the background, outbound, on its own schedule.

`CHAT_TOKEN_ISSUER` was added to settings (matching the decided config shape)
and, in a follow-up pass, is now enforced: `verify_chat_token` passes
`issuer=settings.chat_token_issuer` to `jwt.decode`, so a token with a
different `iss`, or none, is refused whenever the setting is configured;
unset, `iss` is not checked, which keeps the service bootable in
environments that have not been given the monolith's issuer yet
(`tests/test_chat_token_issuer.py`). This goes beyond the acceptance
checklist, which never asked for an `iss` check, but ADR-0009 already
documented `iss` as part of the token's contract, so the verifier now matches
the ADR instead of a checklist that predates it.

`app/services/chat_token_keys.py` also gained its own direct tests
(`tests/test_chat_token_keys.py`): a successful fetch replaces the active
keyset wholesale, a failed one (server error, malformed body, no `keys`
field) leaves it untouched, and no `CHAT_TOKEN_JWKS_URL` makes the refresh
loop a permanent no-op — all against `httpx.MockTransport`, so no real
network call happens in the suite. `tests/test_route_authentication.py` is
new too: it enumerates every route FastAPI publishes and asserts each one
refuses a caller with no credential and a credential that isn't a chat token,
so a route added without the auth dependency fails a test instead of
shipping silently public.

`tests/chat_tokens.py`, `scripts/mint_chat_token.py` (dev-only, per its own
docstring), `.env`/`.env.example`, and `docker-compose.yml` all now sign/hold
a fixed RSA test key pair instead of a shared HS256 secret. Docs updated:
ADR-0009's status line, and the "Débito técnico conhecido" bullets in both
`README.md` and `backend/README.md`.

**Review fix:** `set_active_keyset` fell back to the boot-time
`_bootstrap_keyset` whenever a fetch's keys indexed to an empty dict —
including a *successful* `200 {"keys": []}` response, not just a failed
fetch. Mid-rotation, that silently re-trusted whatever `kid` the service
booted with, even one already revoked by an earlier successful rotation. It
now leaves the active keyset untouched whenever a fetch yields no usable
key, matching the documented "falls back to the last known key set"
behavior for both failed and empty-but-successful fetches
(`test_a_successful_but_empty_fetch_does_not_resurrect_the_bootstrap_key`).
The duplicated kid-indexing logic between `_parse_keyset` and
`set_active_keyset` was also extracted into a shared `_index_by_kid`. Full
suite green (277 tests).
