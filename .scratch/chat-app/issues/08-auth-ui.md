# 08 — Auth UI

**What to build:** A user can register and log in through the browser, the JWT persists across reloads, and unauthenticated users are redirected away from protected routes.

**Blocked by:** 01, 03.

**Status:** ready-for-agent

- [ ] Login form and register form, calling the ticket 03 endpoints via TanStack Query
- [ ] JWT stored in `localStorage` (ADR-0004), read into an auth Context on load
- [ ] Protected routes redirect to login when unauthenticated
- [ ] Logout clears the stored token
- [ ] Tests: successful login stores a token and redirects; invalid credentials show an error; protected route redirects when logged out
