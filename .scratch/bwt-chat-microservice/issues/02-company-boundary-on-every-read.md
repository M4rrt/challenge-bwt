# 02 — Company boundary on every read

**What to build:** No read of any kind crosses a Company. A caller from one Company asking for another Company's Chat, message or Participant gets the same answer as a caller asking for something that does not exist.

In the source module this was a queryset invariant, and its docstring said isolation lived there and nowhere else precisely so no call site had to remember it. Leaving Django removed that floor — ADR-0007 names this the central risk of the architecture. So the replacement is structural, not a filter per call site: every readable entity gets its base query from one constructor that takes the caller's Company from the token, and a read path that does not go through it does not compile into existence.

**Blocked by:** 01.

**Status:** ready-for-agent

- [ ] Every persisted, readable row carries its Company
- [ ] Each readable entity has exactly one base-query constructor, taking the Company from the caller's token
- [ ] A cross-Company request for a Chat, a message list, or a Participant returns not-found, never forbidden — no response distinguishes "exists elsewhere" from "does not exist"
- [ ] The isolation test covers every read path that exists at the end of this ticket, and adding a readable entity later means adding its isolation test
- [ ] A caller whose token carries no Company reaches nothing
