# Spec — BR Wine Tours Chat as a microservice

**Status:** ready-for-agent

**Vocabulary:** this spec uses the glossary in root `CONTEXT.md` — Chat, Company,
Staff Chat, Client Chat, Staff-only Message, Participant, Supervisor. The words
listed there under _Avoid_ do not appear. Where this spec says "the monolith" it
means the BR Wine Tours Django backend; "the service" is this repository's
backend; "the interface" is this repository's frontend.

**Governing ADRs:** [0006](../../docs/adr/0006-session-handoff-via-exchange-code.md),
[0007](../../docs/adr/0007-own-database-company-boundary-in-code.md),
[0008](../../docs/adr/0008-domain-rewritten-in-fastapi.md),
[0009](../../docs/adr/0009-chat-owns-token-in-rs256.md),
[0010](../../docs/adr/0010-no-request-depends-on-the-monolith.md),
[0011](../../docs/adr/0011-revocation-at-the-next-token.md). Lighter decisions
are in `docs/decisions.md` under "BWT monolith integration". Nothing in this spec
overrides them; where it looks like it does, the ADR wins and the spec is wrong.

---

## Problem Statement

BR Wine Tours has a chat built as a Django app inside the monolith and a chat
module embedded in the monolith's React frontend. It never ran in production —
it is a local prototype behind a feature flag — and in that shape it cannot go to
production, for three separate reasons.

It shares the monolith's failure domain. A chat is a long-lived WebSocket per
open tab and a fan-out on every message; that load profile has nothing in common
with the request/response product around it, and the two cannot be scaled,
deployed or rolled back apart. A monolith deploy drops every chat connection.

It has no second client. Native apps are coming, and the only chat interface that
exists is a module inside one React application — so every native feature would
have to be built twice, and the web module would drift from the contract each
time.

And its correctness rests on Django-specific machinery that does not survive
leaving. Company isolation is a queryset invariant; who may read a Staff-only
Message is decided by an `isinstance` check against six `User` subclasses through
multi-table inheritance. Both evaporate the moment the code stops being a Django
app against the monolith's database, and both fail silently when they break — the
known defect in the source module is a Participant loaded through a relation
coming back as the base class, which answered "no" for staff, sometimes dropping
employees from their own fan-out and sometimes keeping an end client in it.

Meanwhile this repository holds a working chat: FastAPI, WebSocket, Redis
pub/sub fan-out, Postgres, Terraform, a React interface, a test suite. It has the
wrong domain (its own user accounts, its own login, a flat Conversation with no
Company, no visibility rules and no supervision) but the right shape.

## Solution

Turn this repository into BR Wine Tours' Chat: one service with its own database
and its own Redis, one interface of its own on its own domain, and the monolith
as the only authority on identity.

**Identity is issued, never held.** The service's own registration, login,
refresh, logout, password hashing and `User` table are deleted. The monolith
gains a dedicated endpoint that issues a short-lived **chat token** signed RS256
with a key id, carrying who the requester is, their Company, their user kind,
their scopes, and enough to display them. The service validates that token
offline against a public key and holds no material capable of minting any token
at all.

**The interface gets its session by handoff.** The monolith's frontend stops
embedding a chat module and instead links out, carrying a single-use, short-lived
exchange code in the URL fragment. The interface redeems the code against the
monolith and receives a renewal credential **scoped to chat** — never the
product's session — plus the API and WebSocket URLs, so every client learns the
service's address from the monolith rather than from a compiled-in constant.

**No request of the service depends on the monolith.** Sending a message, reading
a Chat, keeping a WebSocket up: none of these has a monolith call in them. What
needs fresh data arrives on routes that block nothing — claims in the token,
**commands** the monolith sends, **events** it publishes. Composition (create a
Chat, add or remove a Participant) is validated in the monolith against live
data, including the CRM contact check that cannot be mirrored, and then delivered
to the service as a command that already carries each Participant's identity.
Monolith down therefore means no new Chats and no new Participants, while every
existing Chat keeps sending and receiving.

**The domain is re-derived, not ported.** Chat types, message visibility, read
state, supervision, cursor pagination and idempotency are rebuilt in
FastAPI/SQLAlchemy on top of what this repository already has. Company isolation
and the Staff-only Message rule get tests before they get code, because they are
exactly the two invariants that lost their Django floor.

---

## User Stories

### Session and identity

1. As a Company staff member using the BWT product, I want a chat entry point that
   takes me straight into the Chat interface already signed in, so that I never
   type a second password.
2. As a Company staff member, I want the link that carries me into chat to be
   useless to anyone who later reads my browser history, so that a shared or
   synced machine does not hand over my session.
3. As a Company staff member, I want whatever the Chat interface stores to be
   useless against the rest of the BWT product, so that a compromise of the chat
   interface costs me chat and nothing else.
4. As a Company staff member, I want my chat session to keep working for as long
   as I am using it without re-entering the product, so that a long support shift
   is not interrupted.
5. As a native app user, I want the app to obtain chat access the same way the web
   interface does, so that chat behaves identically wherever I open it.
6. As a native app user, I want the app to learn the chat service's address at
   session time rather than from a version I installed months ago, so that the
   service can move or be switched off without me updating anything.
7. As the platform operator, I want the service to be unable to mint a token that
   anything accepts, so that compromising the service does not let an attacker
   impersonate a user.
8. As the platform operator, I want a chat token to be rejected by the product and
   a product token to be rejected by chat, so that having two tokens is safer than
   having one rather than worse.
9. As the platform operator, I want to rotate the signing key by publishing a new
   key id, so that rotation costs no redeploy of the service and does not
   invalidate tokens already in flight.
10. As the platform operator, I want the service to boot and serve with no network
    access to the monolith, so that a monolith outage cannot prevent the service
    from starting.

### Company isolation

11. As a Company, I want no read of any kind to return another Company's Chat,
    message, Participant or presence, so that my commercial conversations are
    mine alone.
12. As a Company, I want a request for a Chat belonging to another Company to be
    indistinguishable from a request for a Chat that does not exist, so that no
    one can probe for the existence of my Chats.
13. As a developer on this service, I want the Company filter to be impossible to
    forget on a new read path, so that the invariant that used to live in a Django
    queryset does not decay into an `if` somebody has to remember.

### Chat lifecycle and composition

14. As a Company staff member, I want to open a Staff Chat with colleagues, so
    that internal coordination happens where the work is.
15. As a Company staff member, I want to open a Client Chat with an end client, so
    that a negotiation has one thread instead of scattered channels.
16. As a Company staff member, I want the list of people I can start a Chat with
    to reflect who is active in my Company and who is actually a contact of it
    right now, so that I never open a Chat with someone who left last week.
17. As a Company staff member, I want opening a Chat with the same person twice to
    land me back in the existing Chat, so that a 1:1 never splits into two
    threads.
18. As a Company staff member, I want to add a colleague to an existing Chat, so
    that I can bring in whoever the conversation now needs.
19. As a Company staff member, I want to remove a Participant from a Chat, so that
    someone who should no longer be in the conversation stops being in it.
20. As a Company staff member, I want to leave a Chat myself, so that I stop
    receiving a thread that is no longer mine.
21. As a Company staff member, I want a group Chat to carry a name, so that a
    thread with five people is identifiable in a list.
22. As the platform operator, I want a Chat that is born from a business event —
    a negotiation opening — to be created without any browser being involved, so
    that automation and human action use the same path.
23. As a Company staff member, I want composition to fail loudly and change
    nothing when the monolith cannot validate it, so that a Chat is never created
    with a Participant who should not be in it.
24. As a Company staff member, I want the Chat I am adding someone to never to
    accept a stale answer about whether they belong to my Company, so that
    yesterday's employee does not gain today's history.

### Messaging

25. As a Participant, I want to send a message into a Chat and see it appear, so
    that the conversation moves.
26. As a Participant, I want a message I sent to be stored exactly once even if my
    client retried the request, so that a flaky connection does not duplicate what
    I said.
27. As a Participant, I want to read a Chat's history in pages, ordered stably, so
    that scrolling back through a long negotiation neither skips nor repeats a
    message.
28. As a Participant, I want the page boundary to be stable while new messages
    arrive, so that paging back does not shift under me.
29. As a Participant, I want to delete a message I sent, so that I can take back a
    mistake.
30. As a Participant, I want a deleted message to remain visible as a marker
    rather than vanishing, so that the thread does not silently change shape for
    everyone else.
31. As a Company staff member in a Client Chat, I want to write a Staff-only
    Message, so that I can coordinate with colleagues without leaving the thread.
32. As an end client, I want never to receive a Staff-only Message and never to
    learn one exists, so that neither its content nor its presence leaks — not in
    the list, not in a count, not in a gap in pagination.
33. As a Participant, I want to know which messages I have read and which I have
    not, so that I can find where I left off.
34. As a Participant, I want an unread count per Chat, so that I can triage
    without opening everything.
35. As a Participant, I want marking as read never to mark a message that has not
    arrived yet, so that a clock skew on my device does not swallow a Chat's
    unread state.
36. As a Participant, I want a message's sender shown by their current name and
    avatar, so that a rename in the product is reflected in history.
37. As an end client whose account was anonymised in the product, I want my name
    to stop appearing in chat history, so that the erasure is real.

### Supervision

38. As a Supervisor, I want to read my Company's Chats without being added to
    them, so that I can audit or assist without joining every thread.
39. As a Supervisor, I want my reading never to produce a read receipt, so that my
    presence in the audit does not look like participation.
40. As a Supervisor, I want my supervision to be scoped to my own Company, so that
    the scope cannot become a cross-Company key.
41. As a Company staff member, I want the rule about who may read a Staff-only
    Message to answer "no" for any reader it cannot classify, so that an
    unrecognised user kind fails to the narrow side rather than the wide one.

### Realtime

42. As a Participant, I want a message sent by anyone in a Chat to reach my open
    screen immediately, so that the conversation feels live.
43. As a Participant, I want realtime delivery to work no matter which service
    instance I happen to be connected to, so that scaling out is invisible to me.
44. As an end client with a Chat open, I want the realtime stream never to carry a
    Staff-only Message to my connection, so that the visibility rule holds at the
    transport and not only in the API.
45. As a Participant, I want to see who is typing, so that I know to wait.
46. As a Participant, I want to see who is currently online, so that I know whether
    to expect an answer now.
47. As a Participant, I want presence to degrade to "unknown" rather than break the
    Chat when the presence store is unavailable, so that an infrastructure blip
    does not take messaging down.
48. As a Participant, I want my connection to renew its credential without
    dropping, so that I never lose messages to a routine expiry.
49. As a Participant, I want a connection that fails to renew in time to be closed
    with a distinct reason, so that my client renews and reconnects instead of
    sending me to a login screen.
50. As a Company staff member, I want someone removed from a Chat to stop receiving
    its messages immediately rather than at their next reconnect, so that removal
    means removal.
51. As a Participant removed from a Chat, I want my client to be told that
    specifically, so that it stops retrying a room it may not enter.
52. As a Participant, I want a network failure to be distinguishable from an expiry
    and from a revocation, so that my client backs off, renews, or gives up
    correctly in each case.
53. As the platform operator, I want a permission revoked in the monolith to stop
    applying in chat within a bounded, known window, so that "we removed their
    access" has a defensible meaning.
54. As the platform operator, I want an urgent revocation — a dismissal, a ban — to
    take effect before that window elapses, so that the normal path staying simple
    does not cost me the exceptional case.
55. As the platform operator, I want a message to be broadcast only after the
    transaction that wrote it committed, so that nobody is ever notified about a
    message a rollback erased.
56. As the platform operator, I want nothing to be lost if a process dies between
    commit and publish, so that realtime delivery is not a best-effort side
    effect.

### Notifications

57. As a Participant not currently connected, I want to receive a push
    notification about a message addressed to me, so that I do not have to keep the
    chat open.
58. As the platform operator, I want push credentials, device tokens and
    notification wording to stay in the monolith, so that the service knows *when*
    something happened and the monolith decides *whom to tell and how*.
59. As the platform operator, I want the notification path to be one-way and
    asynchronous, so that a notification backlog can never slow down a message
    send.
60. As the monolith, I want each event I consume to carry an identifier I can
    deduplicate on, so that at-least-once delivery does not become
    at-least-twice-notified.

### Identity projection

61. As a Company staff member, I want to search my Chat list by the name of the
    person I am talking to, so that I can find a thread among hundreds.
62. As a Company staff member, I want that search to page correctly, so that a
    filtered list behaves like an unfiltered one.
63. As the platform operator, I want the service to know a user's name without
    ever asking the monolith at request time, so that display never becomes a
    synchronous dependency.
64. As the platform operator, I want a name or avatar changed in the monolith to
    reach chat, so that the projection does not rot.
65. As the platform operator, I want to measure how far behind the projection is,
    so that I find out it has stalled before a user reports a wrong name.
66. As the platform operator, I want the projection to be reloadable in bulk, so
    that a new environment or a corrupted table can be rebuilt without replaying
    all history.

### External integrations

67. As an external system integrated with a Company, I want to post a message into
    a Chat over a signed webhook, so that automated events land in the
    conversation.
68. As a Company, I want the webhook secret to be mine alone, so that another
    Company's integration cannot write into my Chats.
69. As a Company, I want a captured webhook request to stop working shortly after
    it was made, so that a replayed payload does not re-post a message.
70. As a Company, I want a webhook signed by one Company and aimed at another
    Company's Chat to be refused, so that the signature is not the only thing
    standing between tenants.
71. As a Company, I want a webhook with no key identifier to be refused outright,
    so that secret rotation cannot be bypassed by omission.
72. As a Participant, I want a webhook-delivered message to arrive live exactly
    like a human one, so that integrations are first-class in the thread.

### The interface

73. As a Company staff member, I want the Chat interface to be its own application
    on its own domain, so that it can ship on its own cadence and serve every
    client from one contract.
74. As a Company staff member, I want the BWT product to no longer carry its own
    embedded chat, so that there is exactly one web chat to keep correct.
75. As a Company staff member, I want the interface to show my Chats with the last
    message and unread count, so that the list is useful at a glance.
76. As a Company staff member, I want the interface to mark a Staff-only Message
    as visibly staff-only when I write and read one, so that I never mistake the
    thread I am writing into.
77. As a Company staff member, I want to compose and send a message with the
    interface showing it immediately, so that the UI does not feel slower than the
    network.
78. As a Company staff member, I want the interface to recover its own state after
    a reconnect, so that a lift ride does not leave a gap in what I see.
79. As a Company staff member, I want the interface to be usable on a phone
    browser, so that a Chat opened from a link on my phone works.

### Operations

80. As the platform operator, I want the service to have its own database and its
    own Redis, so that a chat fan-out spike cannot evict the product's cache and a
    product maintenance window cannot take chat's realtime down.
81. As the platform operator, I want the service's internal routes to be
    unreachable from the public internet, so that the command path is not a public
    API.
82. As the platform operator, I want a command that arrives without an identified
    acting user to be refused, so that the service credential never becomes an
    omnipotent one.
83. As the platform operator, I want the age of the oldest undelivered outbound
    event as a health metric, so that realtime degradation is observable before a
    user complains.
84. As the platform operator, I want a health endpoint that reflects the service's
    own dependencies only, so that monitoring does not turn a monolith outage into
    a chat alarm.

---

## Implementation Decisions

### Scope of this spec

**Assumption stated for confirmation:** this spec's deliverable is the *service
and its interface* — this repository. The monolith-side work it depends on is
specified here only as an **external contract** (see "Contracts owned by the
monolith" below) and tracked elsewhere, because it lands in a different
repository and this tracker cannot hold it.

### Identity and token

- The service's own authentication is **removed entirely**: registration, login,
  refresh, logout, the `User` model, password hashing, and the refresh-token
  table and its endpoints. The interface's registration and login screens go with
  them.
- The service gains a **token verification module** replacing the current
  symmetric decode: RS256, key selected by `kid`, **mandatory `aud` check**,
  expiry enforced. Public keys come from configuration so the service boots with
  no network; a JWKS URL is consulted opportunistically for rotation and falls
  back to the last known key set. An unknown `kid`, a wrong audience, a missing
  audience, or the `none` algorithm are all rejected.
- Token claims consumed by the service: subject identifier, Company identifier,
  user kind, scopes, display name, avatar. The service derives **no** authority
  from anything not in the token or its own database.
- Token lifetime is fifteen minutes and is the revocation mechanism
  ([ADR-0011](../../docs/adr/0011-revocation-at-the-next-token.md)). A short-lived
  denylist, fed by a monolith event and with entries expiring alongside the token
  they block, exists for the urgent case only.

### Company boundary

- Every persisted row that can be read carries the Company identifier: Chat,
  Participant, Message, read state, identity projection, outbox.
- The Company filter is applied at **one** place per aggregate — a single
  constructor for the base query of each readable entity, taking the caller's
  Company from the token — rather than at each call site. This is the
  FastAPI/SQLAlchemy replacement for the Django queryset invariant named in
  [ADR-0007](../../docs/adr/0007-own-database-company-boundary-in-code.md), and it
  is the seam the isolation tests drive.
- A Chat in another Company is reported as **not found**, never as forbidden,
  matching the existing 404-not-403 decision in `docs/decisions.md`.

### Domain model

- Identifiers are **UUID** throughout, including for identifiers mirrored from
  the monolith, which arrive as opaque values with no foreign key behind them.
- `Chat` carries: Company, type (`staff` | `client`), optional name, timestamps.
- `MessageVisibility` is `all` | `staff_only`. A Staff-only Message is only
  legal in a Client Chat; in a Staff Chat the distinction is meaningless and the
  service rejects it rather than silently accepting it.
- `Participant` carries: Chat, user identifier, Company, role, joined-at,
  left-at, last-read-at, last-read-message.
- `Message` carries: Chat, sender identifier, sender kind, visibility,
  `client_message_id`, body, timestamps, and deletion fields (deleted-at,
  deleted-by, reason). **No message table stores the sender's name, email or
  avatar** — the display name is resolved from the projection when the response
  is built, which is what makes anonymisation in the monolith reach chat history.
- Deletion is a **tombstone**: the row stays because the idempotency constraint
  and the pagination cursor depend on it; the body is cleared and the deletion
  recorded.
- Idempotency is a uniqueness constraint on (Chat, sender, `client_message_id`);
  a repeat returns the original message rather than an error.
- Pagination is a **cursor** over (created-at, id), not an offset. Chat list
  ordering is by last activity, with each Chat's last message fetched by a
  lateral join of one row per Chat rather than a bulk prefetch.
- Read state is clamped to now on write, so a future timestamp cannot mark an
  unarrived message as read.
- Who may read a Staff-only Message is a **single pure predicate** over (user
  kind, Company, Chat type, visibility) with a default-deny branch for an
  unclassifiable reader. It is the one rule with the worst failure history
  ([ADR-0008](../../docs/adr/0008-domain-rewritten-in-fastapi.md)) and it is
  tested as a pure function as well as through the API.

### Composition as a command

- Composition endpoints (create Chat, add Participant, remove Participant) are
  **internal** routes: not routable from the public internet, authenticated by a
  service credential, and requiring a header naming the acting user. Missing that
  header is a refusal, not a default.
- The command **carries each Participant's identity** (identifier, Company, user
  kind, display name, avatar). The service validates the shape of the Chat — that
  a Staff Chat contains no client, that a group has a name, that the 1:1 does not
  already exist — and does not re-check what the caller is the authority on.
- The service exposes **no** public endpoint that creates a Chat or adds a
  Participant, and **no** endpoint that lists candidate participants. That list is
  a CRM fact and stays in the monolith
  ([ADR-0010](../../docs/adr/0010-no-request-depends-on-the-monolith.md)).

### Identity projection

- A `user_profile` projection table keyed by user identifier, carrying Company,
  user kind, display name, avatar, source-updated-at and synced-at.
- Fed by three writes, all inbound: the identity in a composition command, an
  identity event stream, and a bulk load endpoint for initial population and
  rebuild. All three are idempotent and last-writer-wins by source-updated-at, so
  an out-of-order event cannot resurrect a stale name.
- **Transport decision:** the identity event stream arrives on the same internal
  HTTP ingress as commands, at-least-once, deduplicated by event id. A broker was
  the alternative; it is deferred because it would add a second test seam for no
  behaviour this spec needs. The ingress is a thin adapter over the same
  application function, so a broker can be put in front of it later without
  touching the domain.
- The observable health signal is **projection lag**: the largest gap between
  source-updated-at and synced-at. There is no cache hit rate, because there is no
  miss path.

### Realtime

- Fan-out addresses **three groups**: what is computed for one user, what is true
  for everyone in a Chat, and what is true only for the Company's staff in it.
  Staff-only content is published to the staff address; isolation comes from the
  address, not from a filter each future emitter must remember.
- Publishing leaves the request through a **transactional outbox**: the event row
  is written in the same transaction as the message and published by a separate
  drain process. The oldest unpublished row's age is the realtime health metric.
- The WebSocket protocol gains named client and server frames: send message,
  typing, mark read, and token renewal in both directions (a warning before
  expiry, a new token from the client, a confirmation from the service). Renewal
  revalidates both the token and the Chat's authorisation.
- Connections are indexed **by Chat and by user**, so losing access closes exactly
  the affected connections. Room connections revalidate authorisation
  periodically as well as on renewal, which covers deactivation and a lost
  supervision scope, not only explicit removal.
- Three distinct close codes, documented as part of the contract: **token
  expired** (renew and reconnect), **access revoked** (leave, do not retry) and
  **unauthenticated** (do not retry with this credential). Network failure remains
  a plain socket error and stays on exponential backoff.
- Presence stays pure Redis with no table behind it and degrades to `unknown`
  rather than failing a read.

### Webhook

- The webhook survives and is hardened, closing the three gaps recorded in
  `docs/decisions.md`: a **per-Company secret** selected by a mandatory key
  identifier (absent identifier is a refusal), a **signed timestamp** with a short
  acceptance window against replay, and a check that the **target Chat belongs to
  the Company that signed**.
- Verification continues to happen over the raw request body, before any database
  access and before parsing.

### Outbound events

- Exactly one outbound path: the service publishes events the monolith consumes to
  decide push notification. At-least-once, each event carrying an id for
  deduplication on the far side. It is asynchronous, drained from the same outbox,
  and never in a request's path.

### The interface

- Registration, login and the account screens are deleted. The entry point becomes
  a **redemption route** that takes the exchange code from the URL fragment, POSTs
  it to the monolith, and stores the returned chat-scoped credential plus the API
  and WebSocket URLs.
- The API base URL becomes **runtime state from redemption**, not a build-time
  environment constant. The environment variable remains only as a development
  fallback.
- The existing silent-refresh seam in the API client is retargeted: it exchanges
  the chat-scoped credential for a new chat token instead of calling the service's
  own refresh endpoint.
- The interface handles the three close codes distinctly, per ADR-0011.
- The webhook test page stays as a development tool and is updated for the new
  signature recipe.

### Contracts owned by the monolith

Specified here because the service is built against them. They are tracked in the
repositories that own them, each in that repository's own convention:

- **Monolith** — `brwinetours-backend-development/specs/002-chat-service-integration/`
  (Spec Kit: `spec.md` with FR-001..FR-030, `tasks.md` with T001..T054 across ten
  phases). Everything below except the last item lives there.
- **BWT frontend** — `brwinetours-frontend-dev/specs/001-chat-link-out/`
  (`spec.md` + `tasks.md`), covering only the link-out and the removal of the
  embedded module.

- **Chat token issue** — returns a fifteen-minute RS256 token for the
  authenticated user, with the claims listed above.
- **Exchange code issue and redemption** — single-use, short-lived; redemption
  returns the chat-scoped renewal credential and the service's API and WebSocket
  URLs.
- **JWKS** — public keys by `kid`.
- **Composition endpoints** — validate against live data (Company membership,
  active status, and for an end client the CRM contact relation) and then call the
  service's internal command routes with the service credential and the acting-user
  header.
- **Identity event stream and bulk load** — user created, changed, deactivated,
  anonymised.
- **Push notification consumer** — consumes the service's outbound events.
- **Per-Company webhook secret** — generated, distributed and rotated by the
  monolith.
- **CORS** for the chat interface's origin.
- **Removal of the embedded chat module** from the BWT frontend, replaced by a
  link out carrying the exchange code.

---

## Testing Decisions

### What makes a good test here

A good test drives the service the way a client does and asserts what a client can
observe. It names a rule from this spec, not a function. It does not reach into
the session to assert rows, does not assert that a particular service function was
called, and does not assert on the shape of an internal helper — all of which
would freeze a design that is being re-derived rather than ported, and all of
which this repository's existing tests already avoid.

Two invariants get tested **before** they get code, because they are the two that
lost their Django floor and both fail silently:

- **Company isolation.** Every read path has a test in which a caller from another
  Company receives "not found". When a new readable entity is added, that test is
  added with it.
- **The Staff-only Message rule.** An end client never receives one over the API,
  never over the WebSocket, never in a count, and never as a gap in pagination —
  plus the default-deny branch for an unclassifiable user kind, which is the
  concrete re-introduction of the source module's known defect.

### The seams

The intent is to add as close to zero new seams as possible, and to use the ones
this repository already has.

**Seam 1 — the ASGI app, over HTTP and WebSocket (existing, primary).** The
current fixtures already drive the real application through `ASGITransport` with a
per-test transaction rolled back at the end, and WebSocket tests connect through
the same app. Everything in this spec is reachable there: public endpoints,
internal command routes, the webhook, the identity ingress and the WebSocket
protocol are all HTTP surfaces of the same app. The only change needed is to the
test helper: where tests call register-and-login today, they mint a chat token
with a **test key pair** whose public half is loaded into settings. That is a test
helper change, not a production seam — verification stays "a public key from
config", exactly as it runs in production.

**Seam 2 — the outbox drain (new, narrow).** The request no longer publishes, so
the HTTP seam alone can no longer observe realtime. The drain is therefore
exposed as a single callable that processes the pending batch once and returns.
Tests send through the HTTP seam, run one drain tick, and assert on what arrives
on the WebSocket. This is the one seam this work adds; it is a single function
with no arguments beyond a session, and it is what the production process calls in
a loop.

**Seam 3 — the interface, at component boundaries (existing).** Testing Library
against the real components with `fetch` stubbed, as in the existing context and
layout tests. The redemption route, the three close codes and the staff-only
affordance are all testable there. Pure logic that already lives in its own module
— message grouping, chat labelling, webhook signing, token decoding — stays
unit-tested directly, which is the existing pattern and adds no seam.

Deliberately **not** added: a stub monolith server. Outbound events are asserted
as outbox rows, and composition is driven by calling the internal routes directly,
so nothing in the suite needs a second process.

### What gets tested where

- Domain rules that are pure — the Staff-only Message predicate, cursor encoding,
  the read-timestamp clamp — get direct unit tests **as well as** an end-to-end
  test through seam 1. Twice is justified for the Staff-only predicate
  specifically, because the API test proves the rule is wired in and the unit test
  proves the default-deny branch that is hard to reach through the API.
- Token verification gets its own tests through seam 1: wrong audience, missing
  audience, unknown `kid`, expired, `none` algorithm, and a token signed by the
  wrong key are each rejected.
- Idempotency, pagination stability under concurrent writes, and tombstone
  behaviour are tested through seam 1.
- Webhook hardening is tested through seam 1, extending the existing webhook
  tests: stale timestamp, missing key identifier, cross-Company target.
- Realtime is tested through seam 1 plus seam 2: delivery to the right address,
  a Staff-only Message never reaching an end client's connection, in-band renewal,
  the deadline close, and eviction on removal.

### Prior art

`backend/tests/` is the model for seam 1 — the client/db fixtures, the
`httpx_ws` WebSocket tests, and the isolation assertions in the conversation and
message tests. `frontend/src/**/*.test.tsx` is the model for seam 3.

---

## Out of Scope

- **Anything implemented in the monolith.** The contracts above are consumed and
  asserted against; they are not built here.
- **Migrating existing chat data.** The source module never ran in production, so
  there is nothing to move.
- **History from the moment of joining.** A new Participant currently reads
  everything said since the Chat was created. Validating composition against live
  data removed the security argument for changing this, leaving a product decision
  nobody has made. Recorded as open in `docs/decisions.md`; the current behaviour
  stands until someone decides otherwise.
- **The monolith's 365-day non-rotating refresh token.** A real concern, raised
  alongside the access-token lifetime change, but not this service's to fix.
- **Message attachments, threads, reactions, editing, and search over message
  bodies.** None are in the source module's design.
- **An LLM bot, microfrontends, and a CI/CD pipeline**, all previously deferred in
  `docs/decisions.md` and not revived by this work.
- **Replacing this repository's Terraform with production-grade infrastructure.**
  The service reuses what is here; hardening is tracked separately.

---

## Further Notes

### The five open divergences from the proposal

`newchat_service_proposal_01.md` is an independent proposal for the same
extraction, written by someone else and still in "proposed" status. Its internal
contradictions have been resolved in place. Five points where this spec
**deliberately differs** were identified; four remain open and need agreement with
its author before the affected tickets are worked, because all four are expensive
to reverse:

1. **UUID versus sequential integer identifiers.** This spec says UUID.
   Affects ticket 03.
2. **Three fan-out addresses versus two.** This spec says three, adding the
   staff-only address. Affects ticket 07.
3. **The inbound external webhook.** Absent from the proposal; retained and
   hardened here. Affects ticket 14.
4. **A separate chat interface versus repointing the existing BWT frontend at the
   service.** This spec removes the embedded module
   ([ADR-0006](../../docs/adr/0006-session-handoff-via-exchange-code.md)).
   Affects tickets 16 and 17.

**Decided:** the Chat type vocabulary is `staff | client`, not
`internal | negotiation`. `CONTEXT.md` is the source of truth for the domain's
language; a different word in the proposal is a rename there, not a change here.
Ticket 03 is unblocked.

### Ordering constraint for tickets

Token verification is the ancestor of everything: no endpoint in this spec is
reachable, or testable, without a valid chat token, and the test helper that mints
one is used by every later ticket. It is the first tracer bullet. The outbox and
its drain are the second, because realtime cannot be asserted before the drain
exists. Company isolation is not a ticket — it is an acceptance criterion on every
ticket that adds a readable entity.

### The source module's known defect

A Participant loaded through a relation came back as the base `User` rather than
the concrete subclass, so the staff-only rule answered "no" for an employee —
sometimes dropping employees from their own fan-out, sometimes keeping an end
client in it. It is silently re-introducible here in a different form (an
unrecognised user kind claim). The default-deny branch and its test exist for
exactly this.
