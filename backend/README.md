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

1. Install [`uv`](https://docs.astral.sh/uv/) if you don't have it: `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. Copy the env file and adjust if needed: `cp .env.example .env`
3. Start Postgres + Redis: `docker compose up -d`
4. Install dependencies: `uv sync`
5. Apply migrations: `uv run alembic upgrade head`
6. Run the API: `uv run uvicorn app.main:app --reload`
7. Health check: `curl http://localhost:8000/health`

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
