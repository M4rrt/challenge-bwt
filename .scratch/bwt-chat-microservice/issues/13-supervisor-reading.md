# 13 — Supervisor reading

**What to build:** A Supervisor reads their Company's Chats without being a Participant of them, so they can audit or assist without joining every thread — and because they are not a Participant, their reading never produces a read receipt.

The scope is resolved in the monolith, against a permission system the service does not know, and arrives as a claim. The service's job is to honour it and to refuse to let it become a cross-Company key.

**Blocked by:** 04, 06.

**Status:** ready-for-agent

- [ ] A caller carrying the supervision scope reads their Company's Chats without being a Participant
- [ ] Supervised reading produces no read receipt and does not move any watermark
- [ ] Supervision never crosses a Company, whatever the claim says
- [ ] A Supervisor's access to a Staff-only Message follows the same predicate as everyone else's, not a bypass
- [ ] A caller without the scope reads nothing they are not a Participant of
