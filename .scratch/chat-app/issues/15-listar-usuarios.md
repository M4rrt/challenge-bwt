# 15 — Username field + list users (backend)

**What to build:** Registration collects a `username` in addition to email/password, and an authenticated user can list all registered users (id + username) so the frontend can build a participant picker for ticket 09.

**Blocked by:** 03 (needs the `User` model and registration endpoint).

**Priority:** High — blocks ticket 09 (participant picker has no user directory to pick from otherwise).

**Status:** done

- [x] `User` model gains a `username` column (non-null, unique) + Alembic migration
- [x] `POST /auth/register` accepts and requires `username` alongside `email`/`password`; duplicate username rejected (409, same shape as duplicate email)
- [x] `GET /users` — authenticated, returns all registered users as `{ id, username }` (no email, no password hash)
- [x] Tests: register requires/stores username, duplicate username rejected, `GET /users` returns all users for an authenticated caller, `GET /users` rejects an unauthenticated caller

## Comments

Implemented TDD (red-green per cycle):

- `app/models/user.py` — `username` column, unique + indexed.
- Migration `76e24d85b3c1`: adds the column nullable first, backfills any pre-existing dev rows with `user_<id prefix>`, then enforces `NOT NULL` + a unique index — avoids dropping local dev data that predated the column.
- `app/schemas/user.py` — `UserCreate.username: str` (required), `UserRead.username`, new `UserSummary` (`id` + `username`, no email/password) for the list endpoint.
- `app/services/auth.py` — `register_user` now checks both email and username uniqueness, raising a new `UsernameAlreadyRegisteredError` mapped to 409 in `app/routers/auth.py`.
- `app/services/user.py` + `app/routers/users.py` — `GET /users`, authenticated via the existing `get_current_user` dependency, returns every registered user's id + username.
- Updated existing tests (`test_auth.py`, `test_conversations.py`, `test_messages.py`) to pass a `username` on every register call (all 30 backend tests passing).

Known follow-up debt (not fixed here, out of scope): the Insomnia collections under `backend/insomnia/` still POST `/auth/register` without a `username` (and with a password that predates ticket 14's strength policy) — they were already stale before this ticket and need a refresh pass.
