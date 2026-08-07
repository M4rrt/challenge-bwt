# Decisions & Trade-offs

Running log of scope deferrals and "what I'd do with more time" notes, captured as they come up during the challenge. For architectural decisions with real trade-offs, see `docs/adr/` — this file is for lighter-weight deferrals that aren't ADR material.

## Deferred

- **No offline/unread delivery tracking.** Messages persist to Postgres and broadcast over WebSocket to currently-connected participants. A participant who wasn't connected when a message was sent fetches the backlog via REST (`GET /conversations/{id}/messages`) on reconnect — there's no read-receipt or unread-count state. Read receipts are a genuinely separate feature (own state machine, UI, edge cases) that isn't in the mandatory scope or the chosen extras (Auth, Tests). First thing to add with more time.
- **Message ordering has no tiebreaker beyond `created_at`.** `list_messages` (`app/services/message.py`) sorts solely by `Message.created_at`; two messages committed within the same timestamp tick would have undefined relative order. Each `send_message` call does its own sequential `await db.commit()`, so in practice this hasn't been observed, and the ticket 05 spec doesn't call for a tiebreaker. Flagged in code review as a soft spot — the fix would be sorting by `(created_at, id)` or adding a monotonic sequence column, worth doing before this sees concurrent/high-throughput writes.

## Frontend tooling

- **Vite over CRA or Next.js.** CRA is deprecated and slow to iterate on. Next.js was considered — its SSR/file-based routing buys nothing here, since every page requires an authenticated user (no first-paint/SEO benefit to chase), and its API routes would compete with FastAPI for "where does server logic live," muddying the frontend/backend split the challenge asks for. Vite gives a fast dev server with minimal config for a plain SPA.
- **TanStack Query for server state**, over hand-rolled `fetch`/`useEffect` (real time cost re-deriving loading/error/race-condition handling per call) or RTK Query (pulls in Redux for no other reason). SWR would have been an equally reasonable substitute — not picked for any strong reason beyond ecosystem familiarity.
- **WebSocket messages are pushed directly into the TanStack Query cache** (`queryClient.setQueryData`) rather than held in separate local state and merged with REST-fetched history in components. This keeps one code path per conversation's message list instead of every consumer needing its own merge/dedup logic against two sources.
- **No global store (Redux/Zustand/Jotai).** The app's only real state is server data (covered by TanStack Query) and the logged-in user (a small auth Context). There's no cross-cutting client-only UI state that would justify a store — "active conversation" lives in the URL via the router instead.
- **MUI over hand-rolled CSS or a headless kit (Radix/Headless UI).** The chat screen's "MSN Messenger" look (separated, rounded panels; real list/input/button primitives) is faster to get right with a component library that ships those primitives styled out of the box than hand-writing CSS for them from scratch on this budget. A headless kit would still leave every visual decision (spacing, borders, elevation) to write by hand — MUI's theme (`src/theme.ts`) covers the same ground with a handful of palette/shape overrides instead.

## Backend tooling

- **SQLAlchemy 2.0 (async) + Alembic**, over SQLModel (less boilerplate for simple CRUD, but awkward for the join-heavy isolation-check queries this app actually needs) or raw SQL via `asyncpg` (full control, but every query and schema change hand-written). Separate Pydantic schemas from the SQLAlchemy models, rather than merging them as SQLModel does.
- **`uv` for dependency management**, over Poetry (more established, more ceremony, slower installs) or plain `pip`/`requirements.txt` (no real lockfile). Fewer commands to learn while already picking up Terraform and SQLAlchemy for the first time.
- **bcrypt over Argon2id for password hashing.** Argon2id is OWASP's current recommendation and is stronger against GPU/ASIC cracking, but it needs `time_cost`/`memory_cost` tuned for the deployment target rather than working out of the box, and bcrypt is already a direct dependency (passlib pulled it in transitively before being dropped for its own incompatibility with bcrypt>=4 — see git history). Not enough marginal security value here to justify the extra tuning and another dependency swap right after that fix. Worth revisiting if this app handled genuinely sensitive data.
- **Layer-by-role project structure** (`routers/`, `models/`, `schemas/`, `services/`, `core/`), over feature-oriented folders (one per domain area). Feature folders pay off more at team/module scale; at four domain areas and one developer, layer-by-role also matches nearly every FastAPI reference/tutorial, which matters when several of the underlying tools (SQLAlchemy, Alembic, uv) are new. Note either structure keeps the same `messages` → `conversations` dependency (a membership check before persisting) — grouping by feature doesn't remove that coupling, just relocates it.
- **404, not 403, for non-participant access to a conversation's messages.** `POST/GET /conversations/{id}/messages` return 404 "conversation not found" both when the conversation doesn't exist and when the requester isn't a participant, rather than distinguishing with 403. Returning 403 would confirm to an unauthorized user that a given conversation ID exists, which runs counter to the isolation guarantee this app is graded on. The membership check (`ConversationNotFoundError`) is shared by both send and fetch, so the two cases can't drift apart.

## Extras not pursued

Committed extras: Auth (JWT) and Tests, chosen for depth over breadth on an 8-16h budget. LLM bot and microfrontends are stretch goals only if time remains, in that priority. Consciously skipped:

- **Native AWS API Gateway WebSocket** — see ADR-0001.
- **SQS/Kafka message decoupling** — not needed at this scale; the webhook→WebSocket path is synchronous, and Redis pub/sub (ADR-0003) already covers the actual scaling concern a queue would otherwise be justified by (fan-out across instances).
- **Microservices split** — a single FastAPI service is simpler to build, test, and deploy correctly within the budget. Splitting auth/messages/notifications into separate services multiplies IaC, networking, and inter-service auth surface for no functional benefit at this scale.
- **CI/CD pipeline** — not set up; would be the next addition after the LLM bot/microfrontends stretch goals.
- **Observability (structured logs, metrics, tracing)** — not set up; deferred alongside CI/CD.
