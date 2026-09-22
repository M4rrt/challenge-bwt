# 03 — Chat and Participant replace Conversation

**What to build:** The domain speaks the glossary in `CONTEXT.md`. A Chat is a container for messages between a set of Participants, typed `staff` or `client`; a 1:1 is a Chat with exactly two Participants, not a separate concept. A Participant carries the link between a user and a Chat, their read state, and the moment they left it if they did.

Public creation still exists at the end of this ticket — ticket 05 is what replaces it with the command from the monolith. Keeping it here is what lets this slice land green and demoable on its own.

**Blocked by:** 02.

**Status:** ready-for-agent

- [ ] Chat carries Company, type (`staff` | `client`), optional name and timestamps; the words Conversation, Room and Sala appear nowhere
- [ ] Participant carries Chat, user identifier, Company, role, joined-at, left-at, last-read-at and last-read-message
- [ ] A group Chat requires a name; a 1:1 does not
- [ ] Opening a 1:1 that already exists returns the existing Chat rather than creating a second one
- [ ] A Staff Chat containing an end client is rejected — the shape of the Chat is the service's own business to validate
- [ ] A Participant who left stops appearing as a current Participant without their row being deleted
- [ ] Cross-Company isolation tests extended to cover Chat and Participant
