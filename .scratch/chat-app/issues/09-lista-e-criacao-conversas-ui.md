# 09 — Lista e criação de conversas (UI)

**What to build:** A logged-in user sees their conversations and can start a new one (1:1 or group), consuming ticket 04's API.

**Blocked by:** 08, 04.

**Status:** ready-for-agent

- [ ] Conversation list screen, fetched via TanStack Query, showing only the user's own conversations
- [ ] "New conversation" flow — pick participant(s), name required for groups
- [ ] Selecting an existing 1:1 contact reuses the existing conversation (reflects the idempotent backend behavior)
- [ ] Tests: list renders the user's conversations, creating a 1:1 with an existing contact doesn't duplicate it in the UI
