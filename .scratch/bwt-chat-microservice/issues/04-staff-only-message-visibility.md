# 04 — Staff-only Message visibility

**What to build:** A Company staff member writes a Staff-only Message inside a Client Chat and coordinates with colleagues without leaving the thread. The end client does not receive it and does not learn it exists — not in the list, not in a count, not as a gap in pagination.

This is the rule with the worst failure history in the source module: a Participant loaded through a relation came back as the base user class, so an `isinstance` check answered "no" for an employee — sometimes dropping employees from their own fan-out, sometimes keeping an end client in it, and failing silently in both directions. ADR-0008 says it gets a test before it gets code. The re-introducible form here is an unrecognised user kind claim, which is why the predicate has an explicit default-deny branch.

**Blocked by:** 03.

**Status:** ready-for-agent

- [ ] Message visibility is `all` or `staff_only`
- [ ] A Staff-only Message is only legal in a Client Chat; attempting one in a Staff Chat is rejected rather than silently accepted
- [ ] Who may read a Staff-only Message is a single pure predicate over user kind, Company, Chat type and visibility
- [ ] The predicate has an explicit default-deny branch for an unclassifiable reader, tested directly as a pure function
- [ ] An end client's message list never contains a Staff-only Message, their unread count never counts one, and pagination shows no gap where one was
- [ ] A Company staff member in the same Client Chat does read it
