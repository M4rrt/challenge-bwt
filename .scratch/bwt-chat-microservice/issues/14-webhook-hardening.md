# 14 — Webhook hardening

**What to build:** An external system integrated with a Company posts a message into a Chat over a signed webhook, and it arrives live exactly like a human one — but a captured request stops working shortly after it was made, one Company's integration cannot write into another's Chats, and a request that omits the key identifier is refused outright.

These are the three gaps recorded under "Deferred" in `docs/decisions.md`. They were tolerable in a challenge with a global secret and one tenant; they are not in a multi-tenant service. The secret is generated and distributed by the monolith, per Company.

**Blocked by:** 02.

**Status:** ready-for-agent

- [ ] The signature is verified over the raw request body, before any database access and before parsing
- [ ] The secret is selected by a mandatory key identifier; a request with no key identifier is refused, so rotation cannot be bypassed by omission
- [ ] Each Company has its own secret, and a signature from one Company aimed at another Company's Chat is refused
- [ ] The signature covers a timestamp, and a request outside a short acceptance window is refused
- [ ] A valid message is delivered live through the fan-out like any other
- [ ] An invalid signature is rejected before the database is touched
