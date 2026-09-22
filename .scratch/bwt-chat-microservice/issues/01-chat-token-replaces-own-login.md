# 01 — Chat token replaces the service's own login

**What to build:** A caller reaches every existing endpoint with a chat token issued by the monolith, and the service no longer knows what a password is. Registration, login, refresh, logout, the user account table and the refresh-token table are deleted; in their place the service verifies an RS256 token offline against a public key it holds in configuration, and derives the caller — identifier, Company, user kind, scopes, display name, avatar — from the token's claims alone.

This is the first tracer bullet because nothing else in the spec is reachable, or testable, without a valid chat token, and because the swap breaks every existing test's authentication helper at once. It travels alone for that reason.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] Registration, login, refresh and logout endpoints are gone, along with the user account model, the refresh-token model and password hashing
- [ ] A token signed RS256 and selected by `kid` is accepted; the public key comes from configuration so the service boots with no network
- [ ] The `aud` claim is verified and mandatory — a token with the wrong audience, and a token with no audience at all, are both rejected
- [ ] An expired token, an unknown `kid`, a token signed by the wrong key, and a token declaring the `none` algorithm are each rejected
- [ ] A JWKS URL is consulted opportunistically for rotation and falls back to the last known key set; a key set fetch failing never fails a request
- [ ] The caller identity used by every endpoint comes from claims, with no database lookup behind it
- [ ] Tests mint tokens with a test key pair whose public half is loaded into settings — the production path stays "a public key from config", unchanged
- [ ] The existing endpoints and WebSocket handlers all authenticate this way, and the suite is green
