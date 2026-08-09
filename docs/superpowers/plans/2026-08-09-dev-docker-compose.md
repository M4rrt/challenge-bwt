# Dev Docker Compose Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A single `docker compose up` from the repo root brings up Postgres, Redis, the backend (FastAPI, hot-reload), and the frontend (Vite, hot-reload), with no manual `uv run` / `npm run dev` steps and no rebuild needed after editing source files.

**Architecture:** One root-level `docker-compose.yml` with four services (`db`, `redis`, `backend`, `frontend`), built up incrementally. `backend` reuses the existing `backend/Dockerfile`'s `builder` stage (no new backend Dockerfile). `frontend` gets a new dev-only `Dockerfile`. Both app services bind-mount source directories for hot-reload; `frontend` additionally uses a named volume over `node_modules` to avoid host/container binary mismatches.

**Tech Stack:** Docker Compose, `postgres:16-alpine`, `redis:7-alpine`, existing `backend/Dockerfile` (uv + Python 3.12), new `node:22-alpine` image for the frontend, Vite dev server, `uvicorn --reload`.

## Global Constraints

- No TDD for this work — it's infra/config, not application logic. Each task is verified by actually running the relevant `docker compose` command and checking real output (per project convention for `infra/` work).
- Production deployment paths are untouched: `backend/Dockerfile`'s final (non-`builder`) stage, `infra/frontend.tf` (S3+CloudFront), `infra/ecs.tf`. This plan only adds/changes dev-local tooling.
- Each task commits its own work locally (Conventional Commits format), as normal for this execution skill. Nothing is pushed, no PR is opened, and no branch is merged without the user's explicit confirmation at the end of the whole plan (project `CLAUDE.md`'s "never commit without asking" is satisfied at that push/PR/merge boundary, not at every local `git commit`).
- Env var names in the `backend` service must exactly match `backend/app/core/config.py`'s `Settings` fields: `database_url`, `redis_url`, `jwt_secret_key`, `webhook_hmac_secret`, `frontend_origin` (pydantic-settings reads env vars case-insensitively, so `DATABASE_URL` etc. in the compose file is correct).

---

### Task 1: Root `docker-compose.yml` with `db` + `redis`

**Files:**
- Create: `docker-compose.yml` (repo root)
- Delete: `backend/docker-compose.yml`

**Interfaces:**
- Produces: service names `db` (Postgres, published port `5544`, internal `5432`) and `redis` (Redis, published port `6380`, internal `6379`), both with healthchecks — later tasks' services depend on these by name and healthy-condition.

- [ ] **Step 1: Create the root compose file with `db` and `redis`**

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: chat
      POSTGRES_PASSWORD: chat
      POSTGRES_DB: chat
    ports:
      - "5544:5432"
    volumes:
      - chat_db_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U chat"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6380:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  chat_db_data:
```

Save as `docker-compose.yml` at the repo root (same directory as the top-level `README.md`).

- [ ] **Step 2: Delete the old backend-only compose file**

```bash
rm backend/docker-compose.yml
```

- [ ] **Step 3: Verify `db` and `redis` come up healthy**

Run: `docker compose up -d db redis && sleep 6 && docker compose ps`
Expected: both `db` and `redis` rows show `healthy` in the `STATUS` column.

Run: `docker compose down -v`
Expected: containers and the `chat_db_data` volume are removed (clean slate for the next task).

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml
git rm backend/docker-compose.yml
git commit -m "feat(dev): add root docker-compose with db and redis"
```

> **Executed deviation (2026-08-09):** the ports above (`5544`/`6380`) were
> live-blocked by orphaned root-owned `docker-proxy` processes on this
> machine with no container behind them. Landed as a follow-up commit
> (`fix(dev): use temporary host ports for db/redis (5545/6381)`) using
> `5545`/`6381` instead, documented inline in `docker-compose.yml` with the
> exact revert steps. Container-internal ports (`5432`/`6379`, used by
> Task 3's `backend` service via the Docker-internal network) are
> unaffected. Revert once the orphaned processes are cleared.

---

### Task 2: Frontend dev Dockerfile + service

**Files:**
- Create: `frontend/Dockerfile`
- Create: `frontend/.dockerignore`
- Modify: `docker-compose.yml` (add `frontend` service)

**Interfaces:**
- Consumes: nothing from Task 1 (the `frontend` service has no `depends_on` — the browser, not the container, is what talks to the backend, and it does so through the host-published port).
- Produces: service name `frontend`, published port `5173`, serving the Vite dev server with HMR against the bind-mounted `frontend/` source tree.

- [ ] **Step 1: Write the frontend Dockerfile**

```dockerfile
FROM node:22-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
```

Save as `frontend/Dockerfile`.

- [ ] **Step 2: Write the frontend `.dockerignore`**

```
node_modules
dist
```

Save as `frontend/.dockerignore`.

- [ ] **Step 3: Add the `frontend` service to `docker-compose.yml`**

Add this service under `services:`, alongside `db` and `redis`:

```yaml
  frontend:
    build:
      context: ./frontend
    environment:
      VITE_API_URL: http://localhost:8000
    ports:
      - "5173:5173"
    volumes:
      - ./frontend:/app
      - frontend_node_modules:/app/node_modules
```

And add the named volume under the top-level `volumes:` key (alongside `chat_db_data`):

```yaml
  frontend_node_modules:
```

- [ ] **Step 4: Verify the frontend container builds and serves with HMR**

Run: `docker compose up -d --build frontend`
Expected: build succeeds, container starts.

Run: `curl -s http://localhost:5173/ | head -5`
Expected: HTML output containing `<div id="root">` (or similar Vite/React scaffold markup) — confirms the dev server is serving.

Edit `frontend/src/App.tsx` — add a visibly distinct string to the rendered output (e.g. change a heading's text), save the file, then run:
`docker compose logs frontend --tail 20`
Expected: log output shows Vite's HMR message (e.g. `hmr update`) for the edited file, with no container restart. Revert the edit afterward.

Run: `docker compose down -v`
Expected: containers and volumes removed cleanly.

- [ ] **Step 5: Commit**

```bash
git add frontend/Dockerfile frontend/.dockerignore docker-compose.yml
git commit -m "feat(frontend): add dev Dockerfile and compose service"
```

---

### Task 3: Backend dev service (build `builder` stage, hot-reload)

**Files:**
- Modify: `docker-compose.yml` (add `backend` service)

**Interfaces:**
- Consumes: `db` service (name `db`, port `5432` internal) and `redis` service (name `redis`, port `6379` internal) from Task 1. Consumes `backend/Dockerfile`'s `builder` stage (already exists — installs `uv` + all non-dev deps at `/app/.venv`, copies `app/` to `/app/app` and `alembic/` to `/app/alembic`).
- Produces: service name `backend`, published port `8000`, running `alembic upgrade head` then `uvicorn --reload` against the bind-mounted `app/` and `alembic/` directories.

- [ ] **Step 1: Add the `backend` service to `docker-compose.yml`**

Add this service under `services:`:

```yaml
  backend:
    build:
      context: ./backend
      target: builder
    command: sh -c "uv run alembic upgrade head && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
    environment:
      DATABASE_URL: postgresql+asyncpg://chat:chat@db:5432/chat
      REDIS_URL: redis://redis:6379/0
      JWT_SECRET_KEY: change-me
      WEBHOOK_HMAC_SECRET: change-me
      FRONTEND_ORIGIN: http://localhost:5173
    ports:
      - "8000:8000"
    volumes:
      - ./backend/app:/app/app
      - ./backend/alembic:/app/alembic
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
```

- [ ] **Step 2: Verify the backend container builds, migrates, and serves**

Run: `docker compose up -d --build db redis backend && sleep 8`
Expected: all three containers running.

Run: `docker compose logs backend --tail 30`
Expected: log shows Alembic applying migrations (e.g. `Running upgrade ... -> ...`) followed by Uvicorn's startup line (`Uvicorn running on http://0.0.0.0:8000`).

Run: `curl -s http://localhost:8000/health`
Expected: `{"status":"ok"}` (or whatever shape `backend/app/main.py`'s `/health` handler returns — confirm it responds 200, not connection-refused).

- [ ] **Step 3: Verify hot-reload on a backend source edit**

Edit `backend/app/main.py` — add a harmless comment or log line, save, then run:
`docker compose logs backend --tail 10`
Expected: Uvicorn's reload log (e.g. `WatchFiles detected changes ... Reloading...`), no container restart. Revert the edit afterward.

Run: `docker compose down -v`
Expected: clean shutdown.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "feat(backend): add dev docker-compose service with hot-reload"
```

---

### Task 4: Full-stack verification + README updates

**Files:**
- Modify: `backend/README.md` ("Running locally" section)
- Modify: `frontend/README.md` ("Running locally" section)

**Interfaces:**
- Consumes: the complete `docker-compose.yml` from Tasks 1–3 (all four services).
- Produces: nothing consumed by later tasks — this is the last task in the plan.

- [ ] **Step 1: Update `backend/README.md`'s "Running locally" section**

Replace the existing "Running locally" section (currently steps 1–7 starting with installing `uv`) with:

```markdown
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
```

- [ ] **Step 2: Update `frontend/README.md`'s "Running locally" section**

Replace the existing "Running locally" section (currently steps 1–3 starting with copying the env file) with:

```markdown
## Running locally

**With Docker (recommended):**

From the repo root: `docker compose up`

This builds and starts the frontend (with HMR) alongside the backend, Postgres, and Redis. The frontend serves at `http://localhost:5173`.

Editing any file under `src/` is picked up immediately via Vite's HMR — no rebuild, no restart. Adding a new dependency to `package.json` requires `docker compose build frontend` (or `docker compose up --build`) to reinstall.

**Without Docker:**

1. Copy the env file and adjust if needed: `cp .env.example .env`
2. Install dependencies: `npm install`
3. Run the dev server: `npm run dev`

The dev server runs at `http://localhost:5173`.
```

- [ ] **Step 3: Verify the full stack end-to-end**

Run: `docker compose up -d --build`
Expected: all four services (`db`, `redis`, `backend`, `frontend`) start.

Run: `sleep 10 && curl -s http://localhost:8000/health && echo && curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5173/`
Expected: backend health response, then `200` for the frontend.

Run (register a user through the real HTTP path, proving backend+db+redis wiring end-to-end):
```bash
curl -s -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"dockercompose-test@example.com","username":"dockercomposetest","password":"Testpassword123"}'
```
Expected: `201` with a JSON body `{"id": "<uuid>", "email": "dockercompose-test@example.com", "username": "dockercomposetest"}` (per `backend/app/schemas/user.py`'s `UserCreate`/`UserRead` — email, username, and password are all required; password must be 8+ chars with an uppercase letter, a lowercase letter, and a digit or symbol).

Run: `docker compose down -v`
Expected: clean shutdown, no leftover containers (`docker compose ps` shows nothing).

- [ ] **Step 4: Commit**

```bash
git add backend/README.md frontend/README.md
git commit -m "docs: document docker compose as primary local dev workflow"
```

---

## End of plan — push/PR checkpoint

All four tasks are verified and committed locally in this worktree. Before any `git push`, opening a PR, or merging, stop and ask the user for explicit confirmation, listing exactly what changed:
- New: `docker-compose.yml` (root), `frontend/Dockerfile`, `frontend/.dockerignore`
- Deleted: `backend/docker-compose.yml`
- Modified: `backend/README.md`, `frontend/README.md`

Only push/open a PR/merge after the user explicitly says to.
