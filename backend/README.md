# Backend

FastAPI service for the multi-user chat app. See the repo root `CONTEXT.md` and `docs/adr/` for the domain model and architecture decisions behind this code.

## Stack

- FastAPI, served by Uvicorn
- SQLAlchemy 2.0 (async) + Alembic for migrations, PostgreSQL
- Redis for cross-instance WebSocket fan-out (see `docs/adr/0003-redis-pubsub-for-horizontal-scaling.md`)
- `uv` for dependency management

## Project structure

Layer-by-role (see `docs/decisions.md` for why):

```
app/
├── routers/    # API endpoints
├── models/     # SQLAlchemy tables
├── schemas/    # Pydantic request/response shapes
├── services/   # business logic
├── core/       # config, security helpers
├── db.py       # async engine, session, declarative Base
└── main.py     # FastAPI app instance
alembic/        # migration environment (async)
tests/
```

## Running locally

**With Docker (recommended):**

From the repo root: `docker compose up`

This builds and starts Postgres, Redis, the backend (with hot-reload), and the frontend together. The backend runs migrations automatically on startup, then serves at `http://localhost:8000`. Health check: `curl http://localhost:8000/health`.

Editing any file under `app/` or `alembic/` is picked up immediately (no rebuild, no restart) — the container bind-mounts these directories and Uvicorn watches them with `--reload`.

Two exceptions:
- **Dependency changes** (`pyproject.toml`/`uv.lock`): run `docker compose build backend` (or `docker compose up --build`) to reinstall.
- **New Alembic migration**: run `docker compose restart backend` to re-run `alembic upgrade head` (migrations only run once at container start).

**Without Docker:**

1. Install [`uv`](https://docs.astral.sh/uv/) if you don't have it: `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. Copy the env file and adjust if needed: `cp .env.example .env`
3. Start Postgres + Redis: `docker compose -f ../docker-compose.yml up -d db redis`
4. Install dependencies: `uv sync`
5. Apply migrations: `uv run alembic upgrade head`
6. Run the API: `uv run uvicorn app.main:app --reload`
7. Health check: `curl http://localhost:8000/health`

## Webhook

`POST /webhook/messages` lets an external system deliver a message into an existing conversation, authenticated by a shared-secret HMAC signature instead of a JWT.

**Request:**

- Body (JSON): `{ "conversation_id": "<uuid>", "body": "<text>", "source_label": "<string, optional>" }` — `source_label` identifies the external sender in the UI (e.g. `"Shipping Bot"`); omit or send `null` for a generic fallback.
- Header `X-Signature`: hex-encoded `HMAC-SHA256(WEBHOOK_HMAC_SECRET, raw_request_body_bytes)`.

The signature must be computed over the **exact bytes** sent as the request body — re-serializing the JSON (different key order, whitespace) before signing will produce a signature that fails verification, since the server hashes the raw bytes it received rather than re-encoding the parsed payload.

Example (Python):

```python
import hmac, hashlib, httpx

body = b'{"conversation_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6", "body": "Your order shipped!", "source_label": "Shipping Bot"}'
signature = hmac.new(settings.webhook_hmac_secret.encode(), body, hashlib.sha256).hexdigest()

httpx.post(
    "http://localhost:8000/webhook/messages",
    content=body,
    headers={"X-Signature": signature, "Content-Type": "application/json"},
)
```

**Responses:** `401` on a missing/invalid signature (checked before any database access), `404` if `conversation_id` doesn't reference an existing conversation, `201` with the created message on success — delivered live to the conversation's connected participants via the same Redis/WebSocket path as a regular message.

**Known gaps** (see `docs/decisions.md`): no replay protection (a captured valid request can be resent), and no scoped way for the external system to discover which `conversation_id` to use — it must already know the UUID out-of-band.

## Tests

TDD, red-green-refactor per the repo `CLAUDE.md` — tests are written alongside each behavior, not after.

```
uv run pytest
```

## Migrations

```
uv run alembic revision --autogenerate -m "message"
uv run alembic upgrade head
```

`alembic/env.py` reads the database URL from `app.core.config.settings` (i.e. from `.env`), not from `alembic.ini`.
