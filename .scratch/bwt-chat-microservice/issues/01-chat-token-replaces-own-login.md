# 01 — Chat token replaces the service's own login

**What to build:** A caller reaches every existing endpoint with a chat token issued by the monolith, and the service no longer knows what a password is. Registration, login, refresh, logout, the user account table and the refresh-token table are deleted; in their place the service derives the caller — identifier, Company, user kind, scopes, display name, avatar — from the token's claims alone.

This is the first tracer bullet because nothing else in the spec is reachable, or testable, without a valid chat token, and because the swap breaks every existing test's authentication helper at once. It travels alone for that reason.

**Blocked by:** None.

**Status:** ready-for-human

- [x] Registration, login, refresh and logout endpoints are gone, along with the user account model, the refresh-token model and password hashing
- [x] The caller identity used by every endpoint comes from claims, with no database lookup behind it
- [x] Tests mint tokens the way the monolith will, against the same secret the service verifies with — the production path is unchanged
- [x] The existing endpoints and WebSocket handlers all authenticate this way, and the suite is green
- [ ] ~~A token signed RS256 and selected by `kid`~~ — moved to [19](19-chat-token-signed-rs256.md)
- [ ] ~~The `aud` claim is verified and mandatory~~ — moved to [19](19-chat-token-signed-rs256.md)
- [ ] ~~An expired token, an unknown `kid`, a token signed by the wrong key, and the `none` algorithm are each rejected~~ — expiry and wrong-key are covered here; `kid` and `none` moved to [19](19-chat-token-signed-rs256.md)
- [ ] ~~A JWKS URL is consulted opportunistically for rotation~~ — moved to [19](19-chat-token-signed-rs256.md)

## Comments

**Rescoped during implementation.** The signature algorithm and the claims
contract are independent, and only the second one blocks the rest of the spec.
Verification stays HS256 against the shared secret the service already held;
everything about *who the caller is* now comes from the token. The RS256 swap,
the key id, the JWKS and the audience check are [19](19-chat-token-signed-rs256.md).

**What that rescope costs, stated plainly:** a shared secret does not
distinguish verifying from signing, so **this service currently holds material
that can mint a chat token it would itself accept**. That is the precise
property [ADR-0009](../../docs/adr/0009-chat-owns-token-in-rs256.md) was accepted
to remove — so the ADR now describes a guarantee the code does not provide, and
is marked not-yet-implemented for that reason. Until [19](19-chat-token-signed-rs256.md)
lands, compromising the chat service compromises every chat identity. It is a
deliberate, reversible trade for unblocking tickets 02–18; it is **not** safe to
carry into production.

**The claims contract, settled here.** Registered claims carry `sub` and `exp`;
everything the service acts on is namespaced under `https://brwinetours.com/chat`:

```json
{
  "sub": "<user uuid>",
  "exp": 1758547200,
  "https://brwinetours.com/chat": {
    "company_id": "<company uuid>",
    "user_kind": "staff",
    "scopes": ["chat:read", "chat:write"],
    "display_name": "Ana Souza",
    "avatar_url": "https://.../ana.png"
  }
}
```

Namespacing was chosen over flat claims so nothing the service reads can ever
collide with a registered claim the monolith starts issuing later. The RS256
swap does not change any of this.

**`GET /auth/me` survives**, rewritten to echo the caller the token describes. It
is the one endpoint that proves identity comes from claims and nowhere else.

**`GET /users` is deleted here, not in [05](05-composition-arrives-as-a-command.md).**
It listed rows from the user table, so it could not outlive it. The ticket-05 box
"the service exposes no endpoint listing who may participate" is already true.

**Mirrored identifiers lost their foreign keys.** `conversation_participants.user_id`
and `messages.sender_id` pointed at the local `users` table; they are now opaque
UUIDs, as the spec's domain-model section requires.

**One defect surfaced and was fixed.** Authentication no longer makes a database
round-trip, so a WebSocket now connects fast enough to beat the Redis
subscriber's `psubscribe` — a message published in that window was lost. Startup
now waits until the subscriber is listening before the app reports itself ready.

**The interface still calls the deleted endpoints.** Its registration and login
screens are [16](16-interface-session-handoff.md); nothing in this ticket touched
`frontend/`.
