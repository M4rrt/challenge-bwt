# 24 — Refresh token e invalidação de sessão no logout

**What to build:** A user stays logged in across access-token expiry without re-entering credentials, and logging out actually revokes the session server-side instead of only clearing the token client-side. Today `create_access_token` (`app/services/auth.py`) issues a single stateless 60-minute JWT with no way to renew or revoke it early; `logout()` on the frontend (`AuthContext.tsx`) just deletes the token from `localStorage` — the JWT itself stays valid until it naturally expires even after "logout". This ticket adds a server-side-verifiable refresh token alongside the existing access token, consistent with ADR-0004's "simplified auth" scope (still `localStorage`, no httpOnly cookie).

Access token TTL stays at 60 minutes (unchanged). The refresh token is long-lived and does not rotate on use — it stays valid until its own expiry or until explicitly revoked at logout, matching the project's simplified-auth scope over a stricter rotate-and-detect-reuse scheme.

**Blocked by:** None — can start immediately

**Status:** done

- [x] A server-side-verifiable refresh token record (owner user, expiry, revoked state) is persisted at login — opaque and long-lived (e.g. 7 days), separate from the access token's expiry
- [x] `POST /auth/login` returns both an access token and a refresh token
- [x] `POST /auth/refresh` — given a valid, unexpired, non-revoked refresh token, issues a new access token; the refresh token itself is not rotated or replaced
- [x] `POST /auth/refresh` rejects a missing, invalid, expired, or revoked refresh token with 401
- [x] `POST /auth/logout` — revokes the given refresh token server-side, so it can never be exchanged again
- [x] Frontend: `AuthContext` holds the refresh token alongside the access token; any authenticated API call that gets a 401 triggers one silent call to `/auth/refresh`, retries the original request with the new access token, and only forces a full logout (clear storage, redirect to login) if the refresh call itself fails
- [x] Frontend: `logout()` calls `POST /auth/logout` (best-effort — clears local state regardless of the call's outcome) before clearing local storage
- [x] Tests: login response includes both tokens; refresh with a valid token issues a new access token; refresh with an expired/invalid/revoked token is rejected (401); logging out then attempting to refresh with the same token is rejected (401)

## Comments

Implemented TDD (red-green per cycle), reviewed with `/code-review` (Standards + Spec axes), both findings fixed before commit:

- `RefreshToken` model (`app/models/refresh_token.py`) + migration `86b698e95475`: opaque token, sha256-hashed at rest (not bcrypt — high-entropy random token, not a low-entropy password; needs an indexed exact-match lookup bcrypt can't give), owner `user_id`, `expires_at`, nullable `revoked_at`. `refresh_token_expires_days` (default 7) added to `Settings`.
- `app/services/auth.py`: `create_refresh_token`, `refresh_access_token`, `revoke_refresh_token`, sharing a `_find_refresh_token` lookup helper (extracted post-review to remove duplication). `login_user` now returns `(access_token, refresh_token)`.
- `POST /auth/refresh` and `POST /auth/logout` added to `app/routers/auth.py`. `RefreshRequest.refresh_token` is `str | None` (not a bare required `str`) so a request with a missing key is treated the same as an invalid one — 401, not FastAPI's default 422 — matching the ticket's "missing, invalid, expired, or revoked" wording exactly (caught in code review).
- Frontend: `AuthContext` stores both tokens (`chat-app:token`, `chat-app:refresh-token`), registers a refresh handler with `api.ts` via `setRefreshHandler` whenever a refresh token is present. `apiFetch` retries once on 401 through that handler, and — building on that seam — also checks token expiry *proactively* before firing a request (`jwt.ts`'s `isTokenExpired`, using the `jose` npm package's `decodeJwt` to peek at `exp` client-side, no signature check — the backend remains the actual security boundary, this is purely to skip a guaranteed-401 round trip for a token that's visibly already expired). `logout()` fires `POST /auth/logout` best-effort (not awaited, ignores failure) before clearing storage, matching the ticket's stated ordering (caught in code review — the first pass cleared storage first).
- Fixed alongside, found via manual testing of the silent-refresh flow: `useUserSocket.ts` and `useConversationSocket.ts` both closed their WebSocket unconditionally in effect cleanup, including while still `CONNECTING` — harmless but noisy (`WebSocket is closed before the connection is established`), triggered by React StrictMode's dev-only double-invoke and by the WS reconnecting whenever `token` changes (e.g. after a silent refresh). Both now defer the close until the socket reaches `OPEN` if it's still `CONNECTING`.
- Documented in `docs/decisions.md` (Deferred): logout doesn't force-close already-open WebSocket connections, since `websocket.py` validates the JWT once at handshake and never re-checks it — an open connection outlives both the access token's natural expiry and a `POST /auth/logout` call. Noted the concrete fix path (`ConnectionManager` already tracks `user_id -> sockets`, built for `publish_to_user`).
