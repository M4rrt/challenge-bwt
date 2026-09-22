# 11 — WebSocket renewal, eviction and close codes

**What to build:** A Participant's connection survives a routine credential expiry without dropping, and someone who loses access to a Chat stops receiving it immediately rather than at their next reconnect.

An expiring token cannot mean reconnecting: a reconnect costs a recovery query and opens a window in which messages are lost. So the service warns the connection shortly before expiry, the client sends a new token over that same connection, and the service revalidates both the token and the Chat's authorisation. That revalidation is the moment revocation actually happens — the monolith simply does not issue the next token, or issues it without the scope.

The deadline stays as a backstop. Having both is the point: the deadline alone costs a recovery every fifteen minutes, and in-band renewal alone creates a path where forgetting to reschedule the deadline leaves a connection alive forever — and that defect is silent.

**Blocked by:** 07.

**Status:** ready-for-agent

- [ ] The service warns a connection shortly before its credential expires
- [ ] A client sends a new token over the same connection; the service revalidates the token and the Chat's authorisation and confirms, without dropping
- [ ] A connection whose renewal does not arrive by expiry is closed with a dedicated token-expired code, distinct from the unauthenticated one
- [ ] Connections are indexed by Chat and by user, so removing a Participant closes that user's connections in that Chat with a dedicated access-revoked code, leaving their other connections alone
- [ ] Room connections revalidate authorisation periodically as well as on renewal, covering a lost supervision scope and a deactivation, not only explicit removal
- [ ] An event from the monolith can put a token or user on a short-lived denylist whose entries expire alongside the token they block, and closes that user's connections
- [ ] The three close codes are documented as part of the contract
