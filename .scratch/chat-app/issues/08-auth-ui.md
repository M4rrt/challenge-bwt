# 08 — Auth UI

**What to build:** A user can register and log in through the browser, the JWT persists across reloads, and unauthenticated users are redirected away from protected routes.

**Blocked by:** 01, 03.

**Status:** done

- [x] Login form and register form, calling the ticket 03 endpoints via TanStack Query
- [x] JWT stored in `localStorage` (ADR-0004), read into an auth Context on load
- [x] Protected routes redirect to login when unauthenticated
- [x] Logout clears the stored token
- [x] Tests: successful login stores a token and redirects; invalid credentials show an error; protected route redirects when logged out

## Comments

Design doc: `docs/superpowers/specs/2026-08-06-auth-ui-design.md`. Plan: `docs/superpowers/plans/2026-08-06-auth-ui.md`.

Implemented via subagent-driven development, 7 tasks + a final-review fix pass, on branch `ticket-08-auth-ui` (fast-forward merged into `main`):

- `frontend/src/lib/api.ts` — fetch client for `/auth/login` and `/auth/register`, with a typed `ApiError` (status + body).
- `frontend/src/lib/auth/AuthContext.tsx` — hydrates the JWT from `localStorage["chat-app:token"]` on mount, exposes `login`/`logout`/`isAuthenticated`.
- `frontend/src/routes/RequireAuth.tsx` — route guard, redirects to `/login` when unauthenticated.
- `frontend/src/routes/Login.tsx` / `Register.tsx` — controlled forms via TanStack Query `useMutation`, with status-specific error messages (401 / 409 / 422).
- `frontend/src/routes/Conversas.tsx` — protected placeholder route (real conversation list lands in ticket 09), with a logout button.
- Backend: `CORSMiddleware` enabled for `settings.frontend_origin`; wired into `infra/ecs.tf`/`variables.tf` so a deployed backend also gets `FRONTEND_ORIGIN`.
- Frontend test tooling added from scratch: Vitest + React Testing Library, 15 tests across 5 files, all exercising real DOM/router/localStorage behavior with only `../lib/api` mocked.

End-to-end flow (register → login → `/conversas` → reload → logout) verified manually in a browser by the user against the real backend+frontend dev servers.

Known follow-up debt (Minor, deliberately not fixed in this ticket): `api.test.ts` doesn't assert the *absence* of the `Authorization` header when no token is passed; the password-policy error text in `Register.tsx` is a hand-copied duplicate of the backend validator's message (no shared source of truth); 422 on register is treated as "weak password" but would also fire on a malformed email.

(Home → `/login` link added afterward, commit `6493a80`.)

(`Register.tsx`/`api.ts` amended afterward to collect and send `username`, once ticket 15 made it a required registration field.)
