# Decisions & Trade-offs

Running log of scope deferrals and "what I'd do with more time" notes, captured as they come up during the challenge. For architectural decisions with real trade-offs, see `docs/adr/` — this file is for lighter-weight deferrals that aren't ADR material.

## Deferred

- **No offline/unread delivery tracking.** Messages persist to Postgres and broadcast over WebSocket to currently-connected participants. A participant who wasn't connected when a message was sent fetches the backlog via REST (`GET /conversations/{id}/messages`) on reconnect — there's no read-receipt or unread-count state. Read receipts are a genuinely separate feature (own state machine, UI, edge cases) that isn't in the mandatory scope or the chosen extras (Auth, Tests). First thing to add with more time.

## Frontend tooling

- **Vite over CRA or Next.js.** CRA is deprecated and slow to iterate on. Next.js was considered — its SSR/file-based routing buys nothing here, since every page requires an authenticated user (no first-paint/SEO benefit to chase), and its API routes would compete with FastAPI for "where does server logic live," muddying the frontend/backend split the challenge asks for. Vite gives a fast dev server with minimal config for a plain SPA.
- **TanStack Query for server state**, over hand-rolled `fetch`/`useEffect` (real time cost re-deriving loading/error/race-condition handling per call) or RTK Query (pulls in Redux for no other reason). SWR would have been an equally reasonable substitute — not picked for any strong reason beyond ecosystem familiarity.
- **WebSocket messages are pushed directly into the TanStack Query cache** (`queryClient.setQueryData`) rather than held in separate local state and merged with REST-fetched history in components. This keeps one code path per conversation's message list instead of every consumer needing its own merge/dedup logic against two sources.
- **No global store (Redux/Zustand/Jotai).** The app's only real state is server data (covered by TanStack Query) and the logged-in user (a small auth Context). There's no cross-cutting client-only UI state that would justify a store — "active conversation" lives in the URL via the router instead.

## Backend tooling

- **SQLAlchemy 2.0 (async) + Alembic**, over SQLModel (less boilerplate for simple CRUD, but awkward for the join-heavy isolation-check queries this app actually needs) or raw SQL via `asyncpg` (full control, but every query and schema change hand-written). Separate Pydantic schemas from the SQLAlchemy models, rather than merging them as SQLModel does.
- **`uv` for dependency management**, over Poetry (more established, more ceremony, slower installs) or plain `pip`/`requirements.txt` (no real lockfile). Fewer commands to learn while already picking up Terraform and SQLAlchemy for the first time.
- **Layer-by-role project structure** (`routers/`, `models/`, `schemas/`, `services/`, `core/`), over feature-oriented folders (one per domain area). Feature folders pay off more at team/module scale; at four domain areas and one developer, layer-by-role also matches nearly every FastAPI reference/tutorial, which matters when several of the underlying tools (SQLAlchemy, Alembic, uv) are new. Note either structure keeps the same `messages` → `conversations` dependency (a membership check before persisting) — grouping by feature doesn't remove that coupling, just relocates it.

## Extras not pursued

Committed extras: Auth (JWT) and Tests, chosen for depth over breadth on an 8-16h budget. LLM bot and microfrontends are stretch goals only if time remains, in that priority. Consciously skipped:

- **Native AWS API Gateway WebSocket** — see ADR-0001.
- **SQS/Kafka message decoupling** — not needed at this scale; the webhook→WebSocket path is synchronous, and Redis pub/sub (ADR-0003) already covers the actual scaling concern a queue would otherwise be justified by (fan-out across instances).
- **Microservices split** — a single FastAPI service is simpler to build, test, and deploy correctly within the budget. Splitting auth/messages/notifications into separate services multiplies IaC, networking, and inter-service auth surface for no functional benefit at this scale.
- **CI/CD pipeline** — not set up; would be the next addition after the LLM bot/microfrontends stretch goals.
- **Observability (structured logs, metrics, tracing)** — not set up; deferred alongside CI/CD.
