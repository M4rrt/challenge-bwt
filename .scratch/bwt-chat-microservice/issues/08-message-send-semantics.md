# 08 — Message send semantics: idempotency and tombstones

**What to build:** A Participant sends a message and it is stored exactly once even if their client retried, and deleting a message takes back what was said without changing the shape of the thread for everyone else.

Deletion marks, it does not remove: the row stays because the idempotency constraint and the pagination cursor both depend on it existing. The content is cleared and the deletion is recorded with author and reason, and the message keeps appearing in the list as a marker.

**Blocked by:** 03.

**Status:** ready-for-agent

- [ ] A message carries a client message id supplied by the sender
- [ ] Sending the same client message id twice in the same Chat from the same sender returns the original message rather than an error, and stores one row
- [ ] Two different senders may use the same client message id without colliding
- [ ] Deleting a message clears its body and records who deleted it and why, leaving the row in place
- [ ] A deleted message still appears in the list, as a marker, and still occupies its position in the cursor
- [ ] A Participant cannot delete someone else's message
