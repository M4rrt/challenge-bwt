# 12 — Presence and typing

**What to build:** A Participant sees who is online and who is typing, so they know whether to expect an answer now and whether to wait.

Presence stays pure Redis with no table behind it, and keeps the property the source module had: when the presence store is gone, presence degrades to unknown rather than breaking the Chat. Messaging must not depend on it.

**Blocked by:** 07.

**Status:** ready-for-agent

- [ ] A Participant's presence is visible to the other Participants of their Chats
- [ ] Typing is announced to the Chat and expires on its own without an explicit stop
- [ ] Presence and typing never cross a Company
- [ ] With the presence store unavailable, presence reports unknown and sending and reading messages keep working
- [ ] Presence has no table behind it
