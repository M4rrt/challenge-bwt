# 05 — Composition arrives as a command

**What to build:** Creating a Chat and adding or removing a Participant stop being things a browser asks the service to do. The monolith validates them against live data — Company membership, active status, and for an end client the CRM contact relation that cannot be mirrored — and then calls the service with a command that already carries each Participant's identity.

ADR-0010 is what this implements: no request path of the service queries the monolith, and this is the one operation where stale data would hurt most, because whoever joins reads everything said since the Chat was created. The service validates the shape of the Chat and does not re-check what the caller signing the command is the authority on.

**Blocked by:** 03.

**Status:** ready-for-agent

- [ ] Create Chat, add Participant and remove Participant are internal routes, authenticated by a service credential
- [ ] A command arriving without a header naming the acting user is refused — there is no Chat without an author, and this is what stops the service credential becoming an omnipotent one
- [ ] The command carries each Participant's identifier, Company, user kind, display name and avatar
- [ ] The service validates the shape of the Chat and does not attempt to re-validate Company membership or contact status
- [ ] The public endpoints that created a Chat or added a Participant are removed
- [ ] The service exposes no endpoint listing who may participate — that list stays in the monolith
- [ ] With the monolith unreachable, composition fails and every existing Chat keeps sending and receiving normally
