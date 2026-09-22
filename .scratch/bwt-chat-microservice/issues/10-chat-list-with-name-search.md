# 10 — Chat list with search by participant name

**What to build:** A Company staff member finds a thread among hundreds by typing the name of the person they were talking to, and the filtered list pages exactly like the unfiltered one.

This is the ticket that proves the projection earns its place. The source module's filter joined on participant name, and you cannot paginate a list filtered by a column the database does not have — which is why profiles live in the chat's database at all, and why resolving a name is never a call.

The list does not load messages in bulk: each Chat's last message comes from one row per Chat, not from prefetching every collection.

**Blocked by:** 06, 09.

**Status:** ready-for-agent

- [ ] The Chat list is ordered by last activity and carries each Chat's last message and the caller's unread count
- [ ] Each Chat's last message is fetched as one row per Chat rather than by prefetching whole message collections
- [ ] The list filters by participant name, resolved against the projection with no outbound call
- [ ] The filtered list pages by the same cursor contract as the unfiltered one
- [ ] The name filter never matches, or reveals, a name from another Company
- [ ] A Chat's last message respects visibility — an end client never sees a Staff-only Message as the list preview
