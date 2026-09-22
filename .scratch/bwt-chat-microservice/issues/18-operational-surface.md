# 18 — Operational surface

**What to build:** An operator can see the service degrading before a user complains, and the internal command surface is not reachable from the public internet.

Two signals matter and both already exist by this point — the age of the oldest unpublished outbox row, and the projection's lag. This ticket is what turns them into something monitored rather than merely computable, and what makes the health endpoint honest: it reflects the service's own dependencies only, so that a monolith outage does not raise a chat alarm for something chat is still doing fine.

**Blocked by:** 06, 07.

**Status:** ready-for-agent

- [ ] The health endpoint reflects this service's own dependencies only, and never the monolith's availability
- [ ] Oldest-unpublished-outbox-row age and projection lag are both exposed for monitoring
- [ ] The internal command and identity ingress routes are not reachable from the public internet
- [ ] Configuration covers the public key, the JWKS URL, the expected audience and the service credential, with the service booting with no network access to the monolith
- [ ] The service runs against its own database and its own Redis, sharing neither with the monolith
