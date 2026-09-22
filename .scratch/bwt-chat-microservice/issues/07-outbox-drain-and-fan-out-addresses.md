# 07 — Outbox, drain and the three fan-out addresses

**What to build:** Realtime delivery stops being a side effect of the request. The event is written in the same transaction as the message and published by a separate drain, which buys two properties at once: nobody is told about a message a rollback will erase, and nothing is lost if the process dies between commit and publish.

Fan-out addresses three groups rather than one group per Chat with filtering at delivery: what is computed for a single user, what is true for everyone in the Chat, and what is true only for the Company's staff in it. Isolation comes from the address, not from an `if` every future emitter has to remember to write — which is exactly the failure mode ticket 04 exists to prevent, now enforced at the transport.

**Blocked by:** 04.

**Status:** ready-for-agent

- [ ] The outbox row is written in the same transaction as the message it announces
- [ ] A rolled-back transaction produces no delivery
- [ ] The drain is a single callable that processes the pending batch once and returns — this is what tests run between sending and asserting, and what the production process calls in a loop
- [ ] A drain that dies mid-batch loses nothing; the next run delivers what it did not
- [ ] Three fan-out addresses exist: per-user, per-Chat, and per-Chat staff
- [ ] A Staff-only Message is published only to the staff address and never reaches an end client's connection
- [ ] The age of the oldest unpublished row is observable
