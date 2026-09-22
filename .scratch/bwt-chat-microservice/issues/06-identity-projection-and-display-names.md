# 06 — Identity projection and display names

**What to build:** The service knows a user's name and avatar without ever asking the monolith at request time. A profile row exists from the moment someone is added to a Chat, because the command that added them carried it, and an inbound event stream carries the rest of the lifecycle — creation, change, deactivation, anonymisation — so in practice the projection already knows any user before they join anything.

The rule that keeps this honest: no message table stores the sender's name, email or avatar, only their identifier. That is what makes an anonymisation in the monolith reach chat history without the service needing to know what data-protection law is. Denormalising the name "to save a join" breaks it silently.

**Blocked by:** 05.

**Status:** ready-for-agent

- [ ] A profile row carries Company, user kind, display name, avatar, source-updated-at and synced-at
- [ ] Three inbound writes feed it: the identity in a composition command, an identity event, and a bulk load for initial population and rebuild
- [ ] All three are idempotent, and last-writer-wins by source-updated-at, so an out-of-order event cannot resurrect a stale name
- [ ] Identity events arrive on the internal ingress, at-least-once, deduplicated by event id
- [ ] Message responses resolve the sender's display name from the projection at build time
- [ ] No message table has a column holding a name, email or avatar
- [ ] An anonymisation event reaches existing history — past messages stop showing the old name
- [ ] Projection lag — the largest gap between source-updated-at and synced-at — is observable
