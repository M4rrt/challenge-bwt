# Decisions & Trade-offs

Running log of scope deferrals and "what I'd do with more time" notes, captured as they come up during the challenge. For architectural decisions with real trade-offs, see `docs/adr/` — this file is for lighter-weight deferrals that aren't ADR material.

## Deferred

- ~~**No offline/unread delivery tracking.**~~ *(Superseded by ticket 09: a Participant's read state is a watermark on their row — `last_read_at` plus the message it stopped at — moved by `POST /chats/{id}/read`, and every Chat carries the caller's `unread_count`. Read **receipts**, in the sense of telling the sender who has read what, are still absent and still a separate feature.)* Original reasoning: messages persist to Postgres and broadcast over WebSocket to currently-connected participants. A participant who wasn't connected when a message was sent fetches the backlog via REST (`GET /chats/{id}/messages`) on reconnect — there's no read-receipt or unread-count state. Read receipts are a genuinely separate feature (own state machine, UI, edge cases) that isn't in the mandatory scope or the chosen extras (Auth, Tests).
- ~~**Message ordering has no tiebreaker beyond `created_at`.**~~ *(Resolved in ticket 09, and it stopped being a soft spot the moment pagination arrived: the cursor pages over exactly this order, so a pair that sorts one way on one page and the other way on the next is a message skipped or served twice. The order is now `(created_at, id)`, spelled once as `OLDEST_FIRST` in `app/models/message.py` with `NEWEST_FIRST` derived from it — beside the table rather than in `app/services/message.py`, where ticket 09 first wrote it, because ticket 10's chat list previews the newest row in this same order and sits underneath that service in the import graph, and backed by `ix_messages_chat_id_created_at_id`. The identifier was chosen over a sequence column because it is already there and already unique; a v4 uuid says nothing about time, but a tiebreaker only has to be total and stable.)*
- **The chat-list search only sees people who are still in the Chat.** `_matching_the_search` carries `STILL_IN_THE_CHAT` in its `EXISTS`, so once the other person leaves a 1:1 it stops being findable by their name — and a 1:1 has no name of its own to fall back on. Kept that way because every other read means the same thing by "a Participant": `ChatRead.participant_user_ids` shows only current members, so matching a name the response does not carry would be a result nothing on it explains. The alternative is one line (drop the clause), and the argument for it is real — a Chat in your list that no name finds is a Chat you can only reach by scrolling, which is what ticket 10 exists to prevent. Worth revisiting the first time somebody reports it; it needs the response to say *why* a Chat matched before it would be an improvement.
- **The Chat's own name is matched but not indexed.** The `OR` in `_matching_the_search` has two halves: the participant name goes through the GIN trigram index from migration `f2b7d419ac53`, the Chat's name does not, so that half scans. It is bounded by the caller's own Chats rather than by the Company's profiles, which is why it was left — the same index on `chats.name` is the fix if a list of thousands ever makes it matter.
- **`GET /chats` counts SQL statements in one test.** `test_the_preview_costs_the_same_whatever_the_list_is_worth` hooks the engine and asserts that listing five Chats issues as many statements as listing two. The spec's Testing Decisions ask tests to assert what a client can observe and not to reach into the session, and this one does reach in — knowingly. Ticket 10's checklist makes the cost a requirement ("one row per Chat rather than prefetching whole message collections"), an N+1 list is correct in every assertion except the bill, and no response distinguishes one query from thirty. It is the only test in the suite that does this; a second one would be the moment to ask whether the seam belongs in the spec instead.
- **The live chat-list summary gained a message body.** `enqueue_chat_summaries` pushes `ChatRead`, so ticket 10's `last_message` reaches `/websocket/users/me` as well as `GET /chats` — a change to the realtime contract made by a ticket about the list. Deliberate: the alternative is the push and the list disagreeing about the same Chat, which `ChatRead.of` exists to prevent. It also made the Staff-only rule load-bearing on a second path, which `test_the_pushed_summary_never_previews_a_staff_only_message` now covers.
- **`pg_trgm` is installed alongside `unaccent`.** Accent-insensitive search was the agreed decision; the second extension is what makes it indexable. The filter is `ILIKE '%...%'`, and a leading wildcard is exactly what a btree cannot answer, so an expression index without trigrams would have been dead weight. Both are on the allowed list for RDS, and the migration fails loudly rather than silently degrading if a managed Postgres forbids them.
- **The chat-list search matches substrings, not words, and does not rank.** `GET /chats?search=` (ticket 10) matches a case- and accent-insensitive substring against other Participants' `display_name` and the Chat's own name, and returns whatever matches in the list's own order — last activity first. So somebody typing `ana` for "Ana Souza" can get a Chat with "Mariana" in it first, because that one was spoken in more recently. Ranking by `similarity()` (`pg_trgm` is already installed by migration `f2b7d419ac53`) would fix it, but relevance is a second ordering key and the cursor pages over the ordering key — so it is not a filter change, it is a pagination change, and it did not belong in the ticket that introduced the cursor. Substring-without-ranking is the right default in the meantime: a chat list is read by recency, and somebody who typed a name is usually looking for the recent thread with them.
- **`search` reads the projection, so a user the projection has never been told about is unsearchable.** There is no miss path by design (ADR-0010): a name the service has not been sent is simply absent, and a Chat whose only other Participant is such a user can only be found by the Chat's own name. Composition commands carry an identity, so in practice this is a gap only for rows written before ticket 06 or for a Company whose bulk load has not run. The projection-lag metric (`/internal/projection-health`) is what makes it visible.
- **Webhook signature has no replay protection.** `POST /webhook/messages` (ticket 07) verifies an HMAC-SHA256 signature over the raw request body, which proves the payload's integrity and origin but not its freshness — a captured valid request/signature pair can be resent later to re-post the same message. Real protection needs a signed timestamp (or nonce) plus a rejection window, which brings in clock-skew tolerance and (for a nonce) a dedup store. Not in the ticket 07 checklist and low blast radius for this project's threat model (worst case: a duplicate message re-appears), so deferred.
- **No safe way for an external webhook system to discover which chat to post to.** `POST /webhook/messages` (ticket 07) trusts any `chat_id` it's given, gated only by the shared HMAC secret — there's no mechanism for an external integration to enumerate or be scoped to "chats it's allowed to notify." With more time: expose a safe, filtered way for a webhook-integrated system to resolve the right chat (e.g. a lookup by user/participant filter, possibly surfaced in the frontend when a user sets up an integration), rather than requiring the caller to already know the UUID out-of-band.
- ~~**Logout doesn't close already-open WebSocket connections.**~~ *(Superseded by ticket 01: there is no logout, no refresh-token row and no `revoke_refresh_token`. The underlying gap survives in a new shape — a connection is authenticated once, before `accept()`, and never re-checked — and is now [ADR-0011](adr/0011-revocation-at-the-next-token.md)'s in-band renewal plus the three close codes, tracked by ticket 11. Original reasoning kept below.)*
   `websocket.py`'s handlers (`chat_socket`, `user_socket`) validate the JWT once, before `accept()`, and never re-check it afterward — so a connection opened with an access token stays live and keeps receiving real-time messages even after that token's owner logs out (`POST /auth/logout`, ticket 24) or the token naturally expires. `POST /auth/logout` only revokes the refresh token row; access tokens are stateless JWTs with no revocation list, so there's nothing server-side to invalidate mid-connection. In this app it's rarely observable in practice — the frontend closes its own socket on logout via component unmount (`useUserSocket`'s effect cleanup) — but it's real for another tab/device sharing the same access token, or a leaked/captured token. The fix wouldn't need much new plumbing: `ConnectionManager` (`app/services/realtime.py`) already tracks `user_id -> set[WebSocket]` via `connect_user`/`connections_for_user` (built for `publish_to_user`), so `revoke_refresh_token` could look up and force-close that user's active sockets (or publish a `user:{id}` "session revoked" event over the existing Redis pub/sub channel, mirroring how messages already fan out) instead of leaving them open until natural token expiry.

## Frontend tooling

- **Vite over CRA or Next.js.** CRA is deprecated and slow to iterate on. Next.js was considered — its SSR/file-based routing buys nothing here, since every page requires an authenticated user (no first-paint/SEO benefit to chase), and its API routes would compete with FastAPI for "where does server logic live," muddying the frontend/backend split the challenge asks for. Vite gives a fast dev server with minimal config for a plain SPA.
- **TanStack Query for server state**, over hand-rolled `fetch`/`useEffect` (real time cost re-deriving loading/error/race-condition handling per call) or RTK Query (pulls in Redux for no other reason). SWR would have been an equally reasonable substitute — not picked for any strong reason beyond ecosystem familiarity.
- **WebSocket messages are pushed directly into the TanStack Query cache** (`queryClient.setQueryData`) rather than held in separate local state and merged with REST-fetched history in components. This keeps one code path per chat's message list instead of every consumer needing its own merge/dedup logic against two sources.
- **No global store (Redux/Zustand/Jotai).** The app's only real state is server data (covered by TanStack Query) and the logged-in user (a small auth Context). There's no cross-cutting client-only UI state that would justify a store — "active chat" lives in the URL via the router instead.
- **MUI over hand-rolled CSS or a headless kit (Radix/Headless UI).** The chat screen's "MSN Messenger" look (separated, rounded panels; real list/input/button primitives) is faster to get right with a component library that ships those primitives styled out of the box than hand-writing CSS for them from scratch on this budget. A headless kit would still leave every visual decision (spacing, borders, elevation) to write by hand — MUI's theme (`src/theme.ts`) covers the same ground with a handful of palette/shape overrides instead.

## Backend tooling

- **SQLAlchemy 2.0 (async) + Alembic**, over SQLModel (less boilerplate for simple CRUD, but awkward for the join-heavy isolation-check queries this app actually needs) or raw SQL via `asyncpg` (full control, but every query and schema change hand-written). Separate Pydantic schemas from the SQLAlchemy models, rather than merging them as SQLModel does.
- **`uv` for dependency management**, over Poetry (more established, more ceremony, slower installs) or plain `pip`/`requirements.txt` (no real lockfile). Fewer commands to learn while already picking up Terraform and SQLAlchemy for the first time.
- ~~**bcrypt over Argon2id for password hashing.**~~ *(Moot since ticket 01: no password reaches this service, and bcrypt is no longer a dependency. Kept for the reasoning trail.)* Argon2id is OWASP's current recommendation and is stronger against GPU/ASIC cracking, but it needs `time_cost`/`memory_cost` tuned for the deployment target rather than working out of the box, and bcrypt is already a direct dependency (passlib pulled it in transitively before being dropped for its own incompatibility with bcrypt>=4 — see git history). Not enough marginal security value here to justify the extra tuning and another dependency swap right after that fix. Worth revisiting if this app handled genuinely sensitive data.
- **Layer-by-role project structure** (`routers/`, `models/`, `schemas/`, `services/`, `core/`), over feature-oriented folders (one per domain area). Feature folders pay off more at team/module scale; at four domain areas and one developer, layer-by-role also matches nearly every FastAPI reference/tutorial, which matters when several of the underlying tools (SQLAlchemy, Alembic, uv) are new. Note either structure keeps the same `messages` → `chats` dependency (a membership check before persisting) — grouping by feature doesn't remove that coupling, just relocates it.
- **404, not 403, for non-participant access to a chat's messages.** `POST/GET /chats/{id}/messages` return 404 "chat not found" both when the chat doesn't exist and when the requester isn't a participant, rather than distinguishing with 403. Returning 403 would confirm to an unauthorized user that a given chat ID exists, which runs counter to the isolation guarantee this app is graded on. The membership check (`ChatNotFoundError`) is shared by send, fetch and the WebSocket handshake — one spelling in `chat_of_participant`, so the three can't drift apart.

## Extras not pursued

Committed extras: Auth (JWT) and Tests, chosen for depth over breadth on an 8-16h budget. LLM bot and microfrontends are stretch goals only if time remains, in that priority. Consciously skipped:

- **Native AWS API Gateway WebSocket** — see ADR-0001.
- **SQS/Kafka message decoupling** — not needed at this scale; the webhook→WebSocket path is synchronous, and Redis pub/sub (ADR-0003) already covers the actual scaling concern a queue would otherwise be justified by (fan-out across instances).
- **Microservices split** — a single FastAPI service is simpler to build, test, and deploy correctly within the budget. Splitting auth/messages/notifications into separate services multiplies IaC, networking, and inter-service auth surface for no functional benefit at this scale.
- **CI/CD pipeline** — not set up; would be the next addition after the LLM bot/microfrontends stretch goals.
- **Observability (structured logs, metrics, tracing)** — not set up; deferred alongside CI/CD.

## BWT monolith integration

Decisions from converting this repository into BR Wine Tours' chat microservice.
The far-reaching ones became ADRs ([0006](adr/0006-session-handoff-via-exchange-code.md)
through [0011](adr/0011-revocation-at-the-next-token.md)); what is here is lighter.

- **The chat token is still signed HS256, and that is a production blocker.**
  Ticket 01 settled the token's *claims* — the thing every other ticket was
  blocked on — and deliberately left the signature alone, so verification is
  still a shared secret. The consequence is stated plainly because it is easy to
  miss: **the service holds material that can mint a token it would accept**,
  which is the exact property [ADR-0009](adr/0009-chat-owns-token-in-rs256.md)
  was accepted to remove. The ADR is accepted, not shipped. Ticket 19 does the
  swap and must land before production traffic.
- **A chat token with no `exp` is refused, not accepted forever.** The JWT library
  only enforces an expiry it finds, so a token issued without one would verify
  indefinitely. [ADR-0011](adr/0011-revocation-at-the-next-token.md) makes the
  lifetime *the* revocation mechanism, which means a token with no lifetime is a
  token the service cannot take away — so `verify_chat_token` requires the claim
  and `Caller` carries the moment rather than the library discarding it. Ticket 11.
- **Eviction travels a control channel, not the delivery channels.** The socket to
  close is almost never on the instance that handled the removal, so the
  instruction goes over the same Redis as a delivery — but on `control:{company}`
  rather than inside a payload on an existing channel. A delivery names an
  audience and the subscriber forwards it blind; an eviction names *sockets*, and
  no channel name can express "this person, in this one Chat, and none of their
  other connections". Deciding by channel prefix keeps the hot path free of a rule
  to read, which is [ADR-0008](adr/0008-domain-rewritten-in-fastapi.md)'s defect.
  Ticket 11.
- **The revocation denylist is read on the WebSocket paths and not on the API
  path.** Ticket 11 asked for the urgent revocation to close a user's connections,
  and it does — handshake, renewal and the periodic revalidation all consult it.
  The authenticated HTTP routes deliberately do not, so a banned user's existing
  token can still read for up to one token lifetime. The missing piece is one line
  in `get_current_caller`; what it costs is the reason it is absent — a Redis
  round trip on every authenticated request, and a Redis outage turning into a 500
  on every request instead of what the fan-out does today (rows stay pending and
  drain when it returns). Coupling the API's availability to Redis is a bigger
  decision than the ticket that surfaced it. Recorded in `backend/README.md` under
  "Débito técnico conhecido".
- **The chat's own authentication is removed.** `POST /auth/register`,
  `/auth/login`, `/auth/refresh`, the `User` model and password hashing all go.
  The monolith becomes the only place where a password exists.
- **UUID identifiers, not integers.** The source module used a sequential primary
  key. In a multi-tenant service on its own host, a sequential id leaks volume and
  is guessable — and precisely when the participation check stopped being a
  queryset invariant and became ported code. Cost: it breaks the numeric type in
  existing consumers, which is cheapest now, before the native apps consume the
  contract.
- **Its own Redis, not the monolith's.** The monolith uses one Redis for cache and
  dynamic configuration. Sharing it would join the failure domains — a chat
  fan-out spike evicting the monolith's cache keys, a monolith maintenance window
  taking chat's realtime down — right after the database was separated to avoid
  exactly that. Presence stays pure Redis with no table behind it, and keeps the
  property of degrading to `unknown` rather than breaking the chat when Redis is
  gone.
- **CloudFront only for the interface's static assets; API and WebSocket straight
  to the load balancer.** Putting CloudFront in front of the WebSocket would push
  a long-lived connection through a proxy with a timeout of its own, costing money
  without buying cache for traffic that is not cacheable. Sticky sessions stay
  unnecessary: the Redis fan-out
  ([ADR-0003](adr/0003-redis-pubsub-for-horizontal-scaling.md)) is what makes any
  instance equivalent.
- **Fan-out addresses three groups**, rather than one group per chat with
  filtering at delivery: one for what is computed for a single user, one for what
  is true for everyone in the Chat, and one for what is true only for the staff in
  it. Isolation comes from the address, not from an `if` every future emitter has
  to remember to write.
- **Per-company webhook secret, generated and distributed by the monolith.** A
  global secret would let any authorised integration write into any company's
  chat. The alternative considered was the chat generating its own, keeping it in
  one place; it stayed with the monolith for symmetry with the rest of
  provisioning. Recorded consequence: the secret exists on both sides, rotation is
  the monolith's job, and a leak there compromises this service's webhook
  boundary.
- **The three webhook gaps close along with adoption.** They were tolerable in a
  challenge and are not in a multi-tenant service: a signed timestamp with a short
  window against replay, a check that the target chat belongs to the company that
  signed, and refusal of a signature with no key id. See the matching items under
  "Deferred" above, which this work resolves.
- **The profile mirror is fed by events.** A participant's row is created the
  moment they are added to a chat, with name and avatar arriving in the command
  that added them. The event stream carries the full user lifecycle — creation,
  change, deactivation — plus the initial load, so in practice the mirror already
  knows any user before they join any chat.
- **Fan-out leaves the request, through an outbox.** The event is written in the
  same transaction as the message and published by a separate process. That buys
  two properties at once: nobody is told about a message a rollback will erase,
  and nothing is lost if the process dies between commit and publish. The age of
  the oldest unpublished row becomes the realtime health metric — observable
  before a user complains.
- **The client learns the service's address from the monolith.** The session
  redemption response returns the API and WebSocket URLs, rather than the address
  living compiled into each client. That is what allows moving or switching off the
  service without shipping a new version — and native apps cannot be updated on
  demand.
- **Deleting a message marks it, it does not remove it.** The row stays, because
  the idempotency constraint and the pagination cursor depend on it existing; the
  content is cleared and the deletion is recorded with author and reason. A deleted
  message keeps appearing in the list as a marker.
- **No message table stores the writer's name, email or avatar.** Only the sender's
  identifier; the name is resolved from the projection when the response is built.
  That is what makes account anonymisation in the monolith reach chat history
  without chat needing to know what data-protection law is. Denormalising the name
  "to save a join" would break it silently — and it is the concrete answer to the
  personal-data caveat recorded in
  [ADR-0007](adr/0007-own-database-company-boundary-in-code.md).
- **The read timestamp is clamped to now.** Without it, a future date marks as read
  a message that has not arrived yet. Shipped in ticket 09 as `advanced_to`, which
  also refuses to move the watermark **backwards** — two clients on one account (a
  phone at the bottom of the thread, a laptop scrolled up) would otherwise have the
  later mark win, the unread count come back, and the Chat re-notify for messages
  already read. A `read_at` with no timezone is refused rather than guessed at, by
  the same argument the cursor makes about naming an instant.
- **The list does not load messages in bulk**: each chat's last message comes from a
  lateral join of one row per chat, instead of prefetching the whole collection.
- **The chat module embedded in the BWT frontend is removed**, replaced by a link
  out to the interface of its own. Two web interfaces against one contract means
  the second one always falls behind.

### Open

- **History from the moment of joining.** Today whoever joins a chat reads
  everything said since it was created, because reads filter by visibility and
  never by join date. Validating composition in the monolith against live data
  ([ADR-0010](adr/0010-no-request-depends-on-the-monolith.md)) removes the stale
  data risk, so this stopped being a security requirement — but it remains a
  product choice nobody made deliberately: adding a colleague to a three-month
  negotiation and handing over everything is what falls out of a filter by chat.
  The proposal discussed was history from the join date by default, with "share
  history" as an explicit, recordable act by whoever adds.
- **365-day refresh token with no rotation.** It belongs to the monolith, not this
  service, but copying credentials to a second origin multiplies the chances of a
  leak with no way to revoke. Worth raising alongside the access-token lifetime
  change ([ADR-0011](adr/0011-revocation-at-the-next-token.md)).
- **Five divergences from `newchat_service_proposal_01.md` still to agree with its
  author.** The proposal's three internal contradictions — residue of an earlier
  draft in which the service asked the monolith synchronously — have been resolved
  in place: §14's "C5/C6 synchronous with fail closed", §12's S2S-latency and
  projection hit-rate metrics, and §13's phase-4 compatibility proxy, plus a set of
  dangling §15 cross-references and a "three routes" list naming four. What remains
  open are five points where our design deliberately differs, all expensive to
  reverse. One is now **decided**: the Chat type vocabulary stays `staff | client`,
  not `internal | negotiation` — `CONTEXT.md` is the source of truth for the
  domain's language, and a different word in the proposal is a rename there, not a
  change here. Four remain open: UUID against sequential integer identifiers,
  three fan-out addresses against two, the inbound external webhook the proposal
  omits, and a separate chat interface against repointing the existing BWT
  frontend. They are listed under "Further Notes" in
  [the spec](../.scratch/bwt-chat-microservice/spec.md).
