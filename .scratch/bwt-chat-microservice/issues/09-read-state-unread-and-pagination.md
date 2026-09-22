# 09 — Read state, unread counts and cursor pagination

**What to build:** A Participant can find where they left off. Each Chat reports what they have not read, marking as read moves a per-Participant watermark, and history pages back stably no matter how much arrives while they scroll.

Pagination is a cursor over creation time and identifier, never an offset — an offset shifts under new arrivals, which is the one thing a chat guarantees will happen. The read timestamp is clamped to now on write, because without the clamp a future date on a client's clock marks as read a message that has not arrived yet.

**Blocked by:** 03.

**Status:** ready-for-agent

- [ ] Message ordering has a stable tiebreaker beyond creation time
- [ ] History pages by cursor; paging back while new messages arrive neither skips nor repeats a message
- [ ] A Participant's read state is a per-Chat watermark carrying the timestamp and the message it stopped at
- [ ] Marking as read is clamped to now — a future timestamp cannot mark an unarrived message as read
- [ ] Each Chat reports the caller's unread count
- [ ] Read state and unread counts respect visibility: a Staff-only Message never counts for an end client
