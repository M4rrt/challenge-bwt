# 21 — The outbox survives a bad row, and time

**What to build:** Two things the outbox does not survive today. One row that can never be published stops realtime for the whole service, and nothing ever removes a row that has been published.

**One bad row is a full stop, not a degradation.** `drain_once` always takes the oldest pending row. If publishing it fails permanently, `run_forever` catches, sleeps and takes the same row again — for ever — and everything queued behind it never goes out. The service keeps accepting and storing messages, the API keeps answering, and live screens simply stop updating. The row needs a count of how many times it has been tried, and a state it lands in when that count runs out, so that the backlog behind it can move.

**Nothing prunes.** A row is kept with `published_at` set, on purpose: it is the record of what was delivered and when, which is what answers "did that event go out?" after an incident. Kept for ever it is just disk. The drain is already a loop, so the prune belongs there rather than in a second process or a cron nobody remembers.

**Blocked by:** None — [07](07-outbox-drain-and-fan-out-addresses.md) has landed.

**Blocks:** [15](15-outbound-push-events.md). See the note below: today the only thing the drain does is `redis.publish`, where a permanent single-row failure is unlikely; ticket 15 puts an HTTP call to the monolith on the same path, where a `400` on one row is ordinary.

**Status:** ready-for-agent

- [ ] A row records how many times publishing it has been attempted, and the count survives the failure that caused it
- [ ] After a bounded number of attempts the row stops being taken, and the rows behind it drain
- [ ] A row that has stopped being taken is still *visible* as a failure: it leaves `oldest_unpublished_age` but is counted somewhere of its own, so that a stuck delivery does not become a quiet one
- [ ] A transient failure — Redis unavailable, then available — still ends with everything delivered, because attempts are bounded generously enough that a blip does not condemn a row
- [ ] Published rows older than a retention window are removed, by the drain itself, in bounded batches that do not lock the table
- [ ] The retention window is configuration, not a constant compiled into the drain

## Notes

**Do not trade a loud failure for a quiet one.** The point of `oldest_unpublished_age` is that a drain which has stopped is visible before a user complains. Moving a condemned row out of "pending" removes it from that signal, so the count of condemned rows has to become a signal of its own — otherwise this ticket fixes head-of-line blocking by hiding the thing that was blocking. [18](18-operational-surface.md) is what turns both into something monitored; this ticket only has to make both answerable.

**Why the blast radius is larger than the probability, today.** The drain currently does one thing: `redis.publish` of two strings. What fails in practice is the connection, and that fails every row equally — head-of-line blocking changes nothing when nothing would have gone out anyway. A permanent failure of one particular row becomes realistic when the drain has more to do, which is exactly [15](15-outbound-push-events.md): outbound events to the monolith over HTTP, drained from this same outbox, where one row the far side rejects is an ordinary Tuesday.

**Retention is a decision with no obviously right number.** Long enough to investigate an incident found a day or two late; short enough that the table is not the biggest thing in the database. A week is a defensible default and should be configuration so that nobody has to ship a release to change it.
