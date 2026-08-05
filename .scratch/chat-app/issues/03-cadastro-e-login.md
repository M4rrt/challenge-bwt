# 03 — Cadastro e login de usuário

**What to build:** A user can register with email + password and log in, receiving a JWT usable on both REST calls and the WebSocket handshake. TDD: tests alongside each behavior (per `CLAUDE.md`).

**Blocked by:** None — backend scaffold (routers/models/schemas/services/core, db, Alembic) already exists.

**Status:** done

- [x] `User` model (email, hashed password) + Alembic migration
- [x] `POST /auth/register` — creates a user, bcrypt-hashed password
- [x] `POST /auth/login` — verifies credentials, issues a JWT
- [x] `get_current_user` dependency — rejects missing/invalid tokens
- [x] Tests: register succeeds, duplicate email rejected, login issues valid JWT, protected route rejects missing/invalid token
