# 19 — Conversas screen layout pass (UI)

**What to build:** Bring the existing conversas screen (`ConversasLayout`, `Sidebar`, `Conversa`) in line with the updated spec:

- Large lateral (left/right) spacing around the central area of the screen.
- The conversation-list sidebar (`Sidebar.tsx`) stays on the right (already the case) but is sized to roughly 16% of the central area's width instead of the current fixed `320px`.
- The message box (`Conversa.tsx`) stays on the left (already the case).
- Messages in the message box are displayed as `User_name: Message` — reformat from the current "caption line + message(s) below" grouping to an inline sender-prefixed line per message (or per group, whichever reads closer to the spec — use judgment, keep `messageGrouping.ts`'s grouping logic).
- A "Usar webHook" link appears outside/below the conversas screen (footer-style, below the sidebar+message-box area), pointing to `/webhook` (route added in ticket 20 — the link can 404 until then).

Existing data-fetching, real-time socket updates, conversation creation, and logout behavior are unchanged — this is a layout/visual pass.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] `ConversasLayout` applies large lateral padding/margin around the central (message box + sidebar) area
- [ ] Sidebar width is proportional (~16%) to the central area rather than a fixed pixel value
- [ ] Message box (`Conversa.tsx`) renders each message/group as `User_name: Message`
- [ ] "Usar webHook" link rendered outside/below the conversas screen area, linking to `/webhook`
- [ ] Existing ConversasLayout/Sidebar/Conversa tests updated for the new markup and still passing; no behavior regressions (conversation switching, sending messages, new-conversation flow, logout)
