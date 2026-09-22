# 17 — Interface: chat list and thread

**What to build:** The Chat interface works against the new contract end to end: a list of Chats with each one's last message and unread count, a thread that pages back through history, composing and sending with the message appearing immediately, and a visible mark on a Staff-only Message both when writing one and when reading one — so nobody mistakes which thread they are writing into.

It also has to tell three closures apart, because treating them alike breaks in opposite directions: token expired means renew and reconnect, access revoked means leave the Chat and stop retrying, and a network failure means exponential backoff. Treating them all as failure turns every expiry into a growing wait; treating them all as expiry makes the client hammer a Chat it was removed from.

**Blocked by:** 10, 11, 16.

**Status:** ready-for-agent

- [ ] The Chat list shows last message, unread count and ordering by last activity, and filters by participant name
- [ ] A thread pages back through history without skipping or repeating a message
- [ ] Composing shows the message immediately and reconciles with what the service confirms, using the client message id
- [ ] A Staff-only Message is visibly marked when read, and composing one is a deliberate, visible choice
- [ ] The three close codes are handled distinctly
- [ ] After a reconnect the interface recovers its own state, leaving no gap in what the user sees
- [ ] The interface is usable at phone width
