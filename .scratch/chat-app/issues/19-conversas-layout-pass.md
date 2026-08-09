# 19 — Conversas screen layout pass (UI)

**What to build:** Bring the existing conversas screen (`ConversasLayout`, `Sidebar`, `Conversa`) in line with the updated spec:

- Large lateral (left/right) spacing around the central area of the screen.
- The conversation-list sidebar (`Sidebar.tsx`) stays on the right (already the case) but is sized to roughly 16% of the central area's width instead of the current fixed `320px`.
- The message box (`Conversa.tsx`) stays on the left (already the case).
- Messages in the message box are displayed as `User_name: Message` — reformat from the current "caption line + message(s) below" grouping to an inline sender-prefixed line per message (or per group, whichever reads closer to the spec — use judgment, keep `messageGrouping.ts`'s grouping logic).
- A "Usar webHook" link appears outside/below the conversas screen (footer-style, below the sidebar+message-box area), pointing to `/webhook` (route added in ticket 20 — the link can 404 until then).
- The conversation's name is shown at the top of the chat (`Conversa.tsx`), above the message list. Resolve it the same way `Sidebar.tsx`'s `conversationLabel` does: `conversation.name` for a named/group conversation, otherwise the other participant's username for a 1:1.

**Added scope (during implementation, by explicit user request):** move the login form from `/login` to the home route `/`, replacing the placeholder scaffold Home page. `/login` is removed entirely (no alias/redirect kept). A user who is already authenticated and visits `/` is redirected to `/conversas`. All other `/login` references (`RequireAuth`'s unauthenticated redirect, `Sidebar`'s logout redirect, `Register`'s post-signup redirect and "already have an account" link) now point to `/`.

Existing data-fetching, real-time socket updates, conversation creation, and logout behavior are unchanged — this is a layout/visual pass.

**Blocked by:** None — can start immediately.

**Status:** done

- [x] `ConversasLayout` applies large lateral padding/margin around the central (message box + sidebar) area
- [x] Sidebar width is proportional (~16%) to the central area rather than a fixed pixel value
- [x] "Usar webHook" link rendered outside/below the conversas screen area, linking to `/webhook`
- [x] Existing ConversasLayout/Sidebar/Conversa tests updated for the new markup and still passing; no behavior regressions (conversation switching, sending messages, new-conversation flow, logout)
- [x] Login form moved to `/`, replacing the placeholder Home page; `/login` route removed
- [x] Authenticated users visiting `/` are redirected to `/conversas`
- [x] `RequireAuth`, `Sidebar` logout, and `Register`'s post-signup redirect/link updated from `/login` to `/`; all related tests updated and passing
- [x] Conversation name/title shown at the top of `Conversa.tsx`, resolved the same way as `Sidebar.tsx`'s `conversationLabel` (group/named conversation → `conversation.name`; 1:1 → other participant's username)

**Added scope (2026-08-08, via `/grill-me` session, user-referenced MSN Messenger mockup image):** visual pass inspired by the structure/palette of a classic MSN Messenger conversation window — structure and color cues only, no literal MSN text/branding, no new features. Decided item by item during grilling; see Comments for the excluded-scope list.

- [x] `Conversa.tsx` header shows an avatar-placeholder icon (person icon for 1:1, group icon for group conversations — `participant_user_ids.length > 2`) next to the conversation name/title, no status/presence text
- [x] Messages render as a single left-aligned column of boxed "bubbles" (one box per message or per group, keeping `messageGrouping.ts`'s grouping), background tinted per `senderKind` (`me`, `other`, `external` each get distinct treatment)
- [x] `Sidebar.tsx` conversation list header shows a count, e.g. "Conversas (n)", and each item shows a person/group icon using the same `participant_user_ids.length > 2` rule
- [x] "Nova conversa" button moved to the top of the sidebar panel (above the list), with a "+" icon
- [x] "Sair" button restyled with error/red emphasis (MUI `color="error"` or equivalent)

## Comments

Message rendering is per-message (`displayName: body` on every line, matching the spec's literal format), but the group's timestamp and the external-sender tooltip are kept per-group (shown only on the first message of a group) — showing the same timestamp on every message in a group would misrepresent each message's actual time, and repeating the tooltip icon per message would be visual noise for multi-message external groups. `messageGrouping.ts`'s grouping logic is unchanged.

`/webhook` test-page link (ticket 20) lives in `ConversasLayout`'s new footer, satisfying the "outside/below the conversas screen" placement both tickets described.

Code review (Standards + Spec axes, run via two parallel sub-agents against `main`) caught two real regressions in the first pass — both fixed before commit: message timestamps were silently dropped, and the external-sender tooltip was rendering once per message instead of once per group when a group had multiple messages. Also bumped the smallest (`xs`) breakpoint's lateral padding from `2` to `4`, since at `xs: 2` it was identical to the pre-change uniform padding and didn't read as "large" lateral spacing at all.

**Reverted:** the `User_name: Message` reformat of `Conversa.tsx` was reverted per explicit user feedback ("foi mal interpretado" — the implementation misread the intent). `Conversa.tsx`/`Conversa.test.tsx` are back to the pre-ticket caption-line-plus-messages-below rendering. Everything else in this ticket (layout spacing, sidebar width, webhook footer link, login-to-home move) stands. Awaiting clarification on what the correct message format should be before re-attempting that item.

Verified: `tsc -b`, `npx vitest run` (62/62) clean after the revert. No browser-automation tool was available in this session, so no screenshots were taken — manual visual verification against the running app is still recommended before merging.

Conversation title added at the top of `Conversa.tsx`. `conversationLabel` was extracted from `Sidebar.tsx` into a shared `lib/conversationLabel.ts` (with its own unit test) rather than duplicating the resolution logic, since both `Sidebar` and `Conversa` now need it. `Conversa.tsx` reuses the same `['conversations']` query key as `Sidebar`, so React Query serves it from cache without an extra network request in the normal case (both are mounted together under `ConversasLayout`).

Verified again after this addition: `tsc -b`, `oxlint`, `npx vitest run` (67/67) all clean.

**MSN Messenger-inspired visual pass (added 2026-08-08):** decided via `/grill-me` interview after user shared a reference screenshot of a classic MSN Messenger conversation window. Scope is structure/palette inspiration only — not a literal reskin. Confirmed in-scope: (1) `Conversa.tsx` header gets an avatar-placeholder icon (person/group, no status text — no presence data exists in the API); (2) messages render as single-column left-aligned boxes/bubbles per group, tinted by `senderKind` including `external`; (3) `Sidebar.tsx` list gets a "Conversas (n)" count header and person/group icons per item; (4) "Nova conversa" button moves to the top of the sidebar, above the list; (5) "Sair" button gets red/error styling. Group vs. 1:1 is detected via `participant_user_ids.length > 2` (matches the same heuristic `Sidebar.tsx`'s create-conversation form already uses via `isGroup`), since there's no explicit `is_group` field on `Conversation`.

Explicitly excluded, with rationale: "Chamar Atenção" (nudge) button — no backend support, would be a new feature, not a layout change; online/presence status ("ONLINE") — no presence system exists; the italicized personal-status line under the contact name — no such data in the API, and a static placeholder string would be empty decoration; any literal MSN branding/text ("Ouvindo: ...", "Janela de Conversas", "Sair do MSN") — user confirmed this is inspiration only, not a full reskin. Chat bubble alignment is a single left-aligned column (not modern left/right split) — user confirmed this matches the reference image and is "the main inspiration."

Implemented via TDD (Red→Green per cycle, per `CLAUDE.md`). Seams agreed with the user before writing tests, per the `tdd` skill: (A) `Conversa.tsx` header icon (`aria-label` "Conversa individual"/"Conversa em grupo"), (B) `Sidebar.tsx` "Conversas (n)" count heading text, (C) `Sidebar.tsx` per-item person/group icon, (D) "Nova conversa" button's DOM position relative to the list (`compareDocumentPosition`). Each got its own red→green cycle in `Conversa.test.tsx`/`Sidebar.test.tsx`. The bubble backgrounds, avatar-circle styling, "Sair" red styling, and the "+" icon on "Nova conversa" are pure CSS/visual with no new assertable behavior beyond what the existing `data-sender-kind` test already covers, so those were applied directly without a dedicated test cycle (agreed with the user beforehand).

Verified: `tsc -b` clean, `oxlint` clean (one pre-existing unrelated warning in `AuthContext.tsx`), `npx vitest run` 72/72 passing. Also verified in a real running instance (backend `uvicorn` + frontend `vite dev`, driven headlessly with Playwright since `chromium-cli` wasn't available in this environment): registered three users, created a 1:1 and a group conversation, sent messages as each participant plus one via the `/webhook/messages` endpoint (HMAC-signed), and screenshotted both conversations. Confirmed visually: avatar circle with person/group icon in the header, single-column left-aligned bubbles tinted per sender (blue/"me", gray/"other", orange/"external" with the info tooltip), "Conversas (2)" count with per-item icons, "Nova conversa" above the list with a "+" icon, red "Sair" button, "Usar webHook" footer link. No console errors.

One unrelated pre-existing cosmetic issue noticed during the screenshot pass, not in scope here: long usernames in the sidebar list overflow the ~16%-wide panel without truncation/ellipsis (visible with a long generated test username). Not introduced by this change; flagging for a future pass.

**Second visual-polish pass (2026-08-08):** user shared a further-detailed HTML/Tailwind mockup (still MSN-inspired) via `/grill-me`-style back-and-forth. Clarified up front: adapt the *style* only, not the literal mockup text — and re-confirmed the earlier exclusions still stand (no nudge button, no online/presence status, no "ouvindo música" line, no literal MSN branding/text). Two structural pieces from the new mockup were explicitly declined after discussion: an outer window "titlebar" frame wrapping message box + sidebar (kept the current two-panel layout, no enclosing chrome), and the decorative compose-toolbar icons (emoji/attachment/wink) since they'd have no backend function and would read as dead UI.

Scope applied, pure CSS/visual, no new assertable behavior (same precedent as the first MSN pass — applied directly, no dedicated TDD cycle):
- `Conversa.tsx`: contact header gets a sky-blue gradient background band; avatar switches from a flat circle to a bordered rounded-square "frame" (2px border + inset highlight); the compose row (textarea + Enviar) gets a tinted background/border container, and the Enviar button now shares the same gradient button style as Sidebar's "Nova conversa".
- `Sidebar.tsx`: "Conversas (n)" heading shrunk to a small uppercase label with a leading group icon (`aria-hidden`, text/accessible-name unchanged); list items get subtle hover/selected sky tinting and thin divider borders between rows.
- `ConversasLayout.tsx`: the "Usar webHook" footer link is now a rounded pill button (dark blue background, white text, arrow icon) instead of a plain text link — stays a real `<a>`/router `Link` with the same href and accessible name, so no test changes needed.
- Extracted the previously-inline gradient button style (used only by Sidebar's "Nova conversa") into a shared `frontend/src/lib/msnButtonStyle.ts` (`msnButtonSx`), now reused by both "Nova conversa" and "Enviar" for visual consistency, instead of duplicating the same sx object in two files.

Verified: `tsc -b` clean, `oxlint` clean (same pre-existing unrelated `AuthContext.tsx` warning), `npx vitest run` 72/72 passing (no test changes needed — purely visual, no accessible-name or DOM-structure changes). Also verified in the already-running dev instance (backend `uvicorn` + frontend `vite`, both already up in this worktree) via a throwaway Playwright script (`chromium-cli` still unavailable in this environment): registered two new users, created a 1:1 conversation, sent a message, and confirmed visually — gradient header with framed avatar icon, tinted compose row, matching-gradient Enviar/Nova-conversa buttons, uppercase "CONVERSAS (n)" sidebar label with icon, sky-tinted selected list item, red "Sair", and the new pill-style "Usar webHook" footer link. No console errors. The script and its `npm install --no-save playwright` were scratch-only and removed afterward; `package.json`/`package-lock.json` are untouched.

**Added scope (2026-08-08): fixed sidebar width + mobile responsiveness.** Explicit user request, superseding the earlier ~16%-proportional decision (item 2 in the original checklist above): `Sidebar.tsx` now uses a fixed width (`200px`, `220px` from the `lg` breakpoint up) instead of `16%`.

Added responsive behavior for the whole `/conversas` screen, previously not addressed at the component-interaction level (only lateral padding had breakpoints): below the `sm` breakpoint (600px), the sidebar no longer renders inline — it becomes a temporary MUI `Drawer` (`anchor="right"`), opened via a menu (`☰`) `IconButton` shown only at that breakpoint, positioned at the top of `ConversasLayout`'s central area (works regardless of whether a conversation is open, since it lives in the layout rather than in `Conversa.tsx`/`ConversaEmptyState.tsx`). The drawer closes automatically when `conversationId` changes (via a `useEffect` on the route param in `ConversasLayout`), so picking a conversation on mobile immediately shows the chat. At `sm` and above, behavior is unchanged from before (sidebar inline, no drawer/button). Desktop vs. mobile is decided once via `useMediaQuery(theme.breakpoints.up('sm'))` (not CSS-only `display` toggling) specifically to avoid mounting `Sidebar` twice — it owns live queries and a WebSocket connection (`useUserSocket`), so a dual-mount would open two sockets and double-fetch.

**By explicit user request, this scope skipped TDD**: no new tests were written; verification is manual (user will test in the browser). The only test-related change was a necessary regression fix, not new test coverage: jsdom's built-in `window.matchMedia` always reports `matches: false`, which made `useMediaQuery` evaluate to the mobile branch during every test, breaking the existing `ConversasLayout.test.tsx` regression test (it expected 2 WebSocket instances — conversation + user socket — but the user socket never connected because `Sidebar` was unmounted inside a closed drawer). Fixed by overriding `window.matchMedia` in `src/test/setup.ts` to default to `matches: true`, so the entire existing suite keeps observing desktop layout without any test file changes. No mobile-specific test coverage was added for the new drawer behavior itself — that's the part left to manual QA.

Verified: `tsc -b` clean, `npx vitest run` 72/72 passing (same 72 as before — no new tests, one existing regression fixed via the `matchMedia` setup change above). Not yet verified in a running browser at a narrow viewport — that's the manual QA the user is doing next.

**Follow-up adjustments (2026-08-08), same session:** a batch of small explicit CSS/UX tweaks after eyeballing the responsive layout, all pure visual (no test changes beyond what was already needed above):

- Menu button floats top-right (`position: absolute`, `top: 12, right: 16`) inside the message-box wrapper `Box` in `ConversasLayout`, lining up with the conversation-name row in `Conversa.tsx`'s header without living inside that component — stays reachable at the same corner from `ConversaEmptyState` too.
- The `Drawer`'s own `slotProps.paper` carries the sky gradient directly (`linear-gradient(to bottom, rgb(224 242 254 / 0.9), rgb(186 230 253 / 0.5))`), so the whole drawer surface is tinted, not just `Sidebar`'s internal `Paper`.
- `Conversa.tsx`'s outer `Paper`: dropped its own `p: 2`/`gap: 2` (header, message list, and compose row now sit flush against the Paper's edges and each other) and halved its corner radius (`borderRadius: 0.5`). The header's now-unneeded `mx: -2, mt: -2` cancel-padding hack was removed along with it.
- Message-list `Box` gained `pl: 2` and `pt: 2` (left/top breathing room only — right/bottom stay flush, per the padding-removal above).
- `TextField` got a placeholder, "Adicione sua mensagem aqui".
- Added a shared `frontend/src/lib/scrollbarStyle.ts` (`skyScrollbarSx`) applied to the message-list `Box` and `Sidebar.tsx`'s list `Paper`; colors lightened after user feedback ("cor mais clara") to track `rgb(240 249 255 / 0.6)`, thumb `rgb(186 230 253 / 1)`, thumb-hover `rgb(125 211 252 / 1)`.
- Compose row: `borderRadius: 0` (was `1`) and `borderColor` changed from the `divider` token to the explicit `rgb(125 211 252 / var(--tw-border-opacity, 1))` — the same sky-300 value already used for the "me"-bubble border elsewhere in this file.

Verified after each change: `tsc -b` clean, `oxlint` clean, `npx vitest run` 72/72 passing.

**Follow-up adjustments (2026-08-08), same session — second batch.** Further small explicit tweaks after the batch above, mostly pure CSS/JSX with one real behavior addition; all in `Sidebar.tsx` unless noted:

- Sidebar list/form height capping: conversation `List` and the "Nova conversa" participants form `Box` each capped at `maxHeight: '50%'` (own `overflowY: 'auto'`) while the form is open, so neither pushes the other off-screen; `Sidebar`'s outer `Paper` got `height: '100%'` so the `50%` resolves correctly both inline and inside the mobile `Drawer`.
- "Nova conversa" form reshuffle: ellipsis truncation on conversation-list item names and participant checkbox labels (needed `minWidth: 0` at each flex level, since flex items default to a content-based min-width that defeats `text-overflow: ellipsis`); a `Divider` between the list and the form; a "Nova Conversa:" title above "Participantes"; "Nome do grupo" moved before the participant checkboxes; form split into a fixed header + an inner scrollable checkbox list + a fixed "Criar" button outside that inner scroll.
- "Criar" now shares `msnButtonSx` with "Nova conversa"/`Conversa.tsx`'s "Enviar" for visual consistency across the three primary-action buttons.
- "Nome do grupo" gets an explicit white background.
- Extracted `frontend/src/lib/textFieldStyle.ts` (`skyTextFieldSx`): white background plus `rgb(125 211 252 / var(--tw-border-opacity, 1))` border color on both hover and focus, applied to both text fields on this screen. Along the way fixed a `Sidebar.test.tsx` regression caused by an external label→placeholder change on the group-name field (`getByLabelText` → `getByPlaceholderText`).
- Added a red (`error.main`) close (X) button to the "Nova conversa" form via a new `handleCloseForm`, since there was previously no way to close the form without submitting it.
- **Real behavior change, done via TDD:** creating a conversation now navigates to `/conversas/:id` (new `onSuccess` handler on `createMutation`); RED/GREEN cycle added `Sidebar.test.tsx`'s "navigates to the new conversation after creating it", and fixed a resulting regression in the pre-existing "does not duplicate an existing 1:1 conversation..." test by adding a `/conversas/:conversationId` route to its render helper (the new navigation had been unmounting `Sidebar` entirely). Also shrunk "Nova conversa"'s button text (`fontSize: '0.75rem'`, that button only).
- Fixed the conversation `List`'s overflow containment: it had `flex: 1` but no `minHeight: 0`/`overflowY`, so a long list grew past the available space and forced the whole outer `Paper` to scroll as a unit instead of the list scrolling internally. Given `minHeight: 0` and `overflowY: 'auto'` unconditionally (previously only set while the form was open), plus `skyScrollbarSx` for consistency.

Verified after each change: `tsc -b` clean, `oxlint` clean, `npx vitest run` passing throughout (72/72 through most of this batch, 73/73 from the navigate-on-create addition onward, which added one new test).
