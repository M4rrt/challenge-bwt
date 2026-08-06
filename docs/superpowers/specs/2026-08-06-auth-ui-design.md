# Auth UI — Design

Ticket: `.scratch/chat-app/issues/08-auth-ui.md`

## Goal

A user can register and log in through the browser, the JWT persists across reloads, and unauthenticated users are redirected away from protected routes.

## Architecture

- `frontend/src/lib/api.ts` — thin wrapper over `fetch`. Prefixes requests with `VITE_API_URL`, sets `Content-Type: application/json`, attaches `Authorization: Bearer <token>` when a token is present, throws on non-2xx with the parsed error body attached.
- `frontend/src/lib/auth/AuthContext.tsx` — React Context + Provider. State: `token: string | null`, hydrated from `localStorage["chat-app:token"]` on mount (per ADR-0004). Exposes `login(token: string)`, `logout()`, `isAuthenticated: boolean`.
- `frontend/src/routes/Login.tsx` — controlled form (email, password), `useMutation` (TanStack Query) calling `POST /auth/login`.
- `frontend/src/routes/Register.tsx` — controlled form (email, password), `useMutation` calling `POST /auth/register`.
- `frontend/src/routes/RequireAuth.tsx` — route guard. No token → `<Navigate to="/login" replace />`. Token present → renders `<Outlet />`.
- `frontend/src/routes/Conversas.tsx` — new placeholder route, protected, shows a logout button. Will be replaced by the real conversation list in ticket 09.
- `frontend/src/App.tsx` — adds `/login`, `/register` (public) and `/conversas` (wrapped by `RequireAuth`) routes. `AuthProvider` wraps the router.
- Backend: `backend/app/main.py` adds `CORSMiddleware`, allowed origin from new `settings.frontend_origin` (default `http://localhost:5173`, added to `Settings` in `backend/app/core/config.py` and `.env.example`).

## Data flow / error handling

- **Login**: submit → `POST /auth/login` → success: `Token{access_token}` → `auth.login(token)` (writes `localStorage` + Context) → `navigate("/conversas")`. Failure (401): inline error message, no navigation.
- **Register**: submit → `POST /auth/register` → success (201): `navigate("/login")` (no auto-login). Failure (409 duplicate email, 422 validation): inline error message.
- **RequireAuth**: checks `isAuthenticated` from Context only. Does not call `/auth/me` to validate the token server-side — out of scope for this ticket; a request rejected later with 401 is handled by whichever ticket adds that call.
- **Logout**: button on `/conversas` calls `auth.logout()` (clears `localStorage` + Context) → `navigate("/login")`.

## Testing (Vitest + React Testing Library)

New dev dependencies: `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`, `jsdom`. Config in `vitest.config.ts` (or a `test` block in `vite.config.ts`) + `src/test/setup.ts` (imports `@testing-library/jest-dom`). `npm run test` script added to `package.json`.

HTTP calls in tests are mocked directly (`vi.fn()` on `api.ts` functions or global `fetch`) — no MSW, to avoid an extra dependency for a handful of HTTP calls.

Cases (per ticket checklist):

- Successful login stores a token (`localStorage` + Context) and navigates to `/conversas`.
- Invalid credentials (401) show an inline error, no navigation, no token stored.
- `RequireAuth` redirects to `/login` when there is no token.
- `AuthContext` hydrates `isAuthenticated` from an existing `localStorage` token on mount.

## Out of scope

- Token expiry / refresh handling.
- Calling `/auth/me` to validate the token is still good.
- Any styling beyond plain functional markup — this is a challenge project, not a design pass.
