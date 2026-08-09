# Dev Docker Compose — Design

Ticket: `.scratch/chat-app/issues/25-infra-hardening-producao.md` (follow-up: root README §Infraestrutura como código requires "Utilize Docker para subir todas as dependencias necessárias para executar as aplicações localmente")

## Goal

A single `docker compose up` from the repo root brings up Postgres, Redis, the backend (FastAPI, hot-reload), and the frontend (Vite, hot-reload) — no manual `uv run` / `npm run dev` steps required. Editing source files on the host is reflected live in both containers with no rebuild or restart. Production deployment (S3+CloudFront for frontend, ECS for backend) is untouched — this is dev-only tooling.

## Architecture

- **`docker-compose.yml`** (new, repo root) — replaces `backend/docker-compose.yml`, which only had `db`+`redis`. Four services:
  - `db` (`postgres:16-alpine`) and `redis` (`redis:7-alpine`) — migrated as-is from `backend/docker-compose.yml`: same ports (5544, 6380), same healthchecks, same named volume for Postgres data.
  - `backend` — `build: { context: ./backend, target: builder }` against the existing `backend/Dockerfile` (no new Dockerfile; the `builder` stage already has `uv` + all deps installed at `/app/.venv`, `--no-dev` only excludes test-only deps like `pytest`, which aren't needed to run the app). `command: sh -c "uv run alembic upgrade head && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"`. Volumes: `./backend/app:/app/app` and `./backend/alembic:/app/alembic` only (not the whole `./backend` directory — that would shadow the image's `/app/.venv`). `depends_on: db (healthy), redis (healthy)`. Environment points at in-network service names instead of `localhost` (`DATABASE_URL=postgresql+asyncpg://chat:chat@db:5432/chat`, `REDIS_URL=redis://redis:6379/0`), plus `JWT_SECRET_KEY=change-me`, `WEBHOOK_HMAC_SECRET=change-me` (same placeholder convention as `backend/.env.example`), `FRONTEND_ORIGIN=http://localhost:5173`. Port `8000:8000` published.
  - `frontend` — new `frontend/Dockerfile` (dev-only, single stage, `node:22-alpine`): `WORKDIR /app`, `COPY package*.json ./`, `npm ci`, `CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]`. Compose mounts `./frontend:/app` for live source edits, plus a named volume over `/app/node_modules` so the container's Linux-native `node_modules` isn't shadowed by the host's (which may be built for a different OS/arch). `environment: VITE_API_URL=http://localhost:8000` (the browser talks to the backend via the host-published port, not the Docker-internal network — `VITE_API_URL` is baked into client-side JS that runs in the browser). Port `5173:5173` published.
  - New `frontend/.dockerignore` (`node_modules`, `dist`).

- `backend/docker-compose.yml` is deleted (superseded by the root file).

## Update semantics (documented in both READMEs)

1. **Source code changes** (`backend/app`, `backend/alembic`, anything under `frontend/`) — automatic. Bind mounts make host edits visible instantly inside the container; Vite HMR and `uvicorn --reload` pick them up with no action needed.
2. **Dependency changes** (`frontend/package.json`, `backend/pyproject.toml`/`uv.lock`) — require `docker compose build <service>` (or `docker compose up --build`), since deps are installed at image-build time, not through the bind mount.
3. **New Alembic migration** — requires `docker compose restart backend`, since `alembic upgrade head` only runs once at container start, before `uvicorn` launches.

## Docs

- `backend/README.md` "Running locally": docker-compose-from-root becomes the primary path; the existing manual `uv run` steps stay as a documented alternative for running without Docker.
- `frontend/README.md` "Running locally": same treatment, `npm run dev` steps kept as the non-Docker alternative.
- Both READMEs get the three update-semantics bullets above.

## Testing

No TDD — this is infra/config, not application logic (consistent with how `infra/` work in this project is verified). Verification is running `docker compose up` for real and confirming:
- All four services start; `db`/`redis` report healthy.
- Backend migrations apply; `curl http://localhost:8000/health` succeeds.
- Frontend loads at `http://localhost:5173` and successfully calls the backend (e.g. register/login) from the browser.
- Editing a backend `.py` file triggers a reload without restarting the container; editing a frontend source file triggers HMR without a page reload.

## Out of scope

- Any change to `backend/Dockerfile`'s production (final) stage, `infra/frontend.tf`, or `infra/ecs.tf` — production deployment strategy is unchanged.
- Running tests inside the backend container (dev dependencies like `pytest` stay excluded from the `builder` stage's install).
- A production-mode Dockerfile/nginx image for the frontend — the frontend has no containerized deployment target; production stays static S3+CloudFront.
