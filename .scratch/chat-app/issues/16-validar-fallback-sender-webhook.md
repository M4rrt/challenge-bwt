# 16 — Validar fallback de remetente do webhook contra a implementação real da 07

**What to build:** Ticket 10 implements the chat screen's sender-fallback for messages with `sender_id: null` as `source_label ?? 'Bot'` (`frontend/src/lib/messageGrouping.ts`), written ahead of ticket 07 (webhook ingestion) actually existing, based only on the `MessageRead` schema shape. Once 07 is implemented, verify the webhook path actually produces `sender_id: null` + a populated `source_label` as assumed, and that the fallback reads correctly end-to-end (a webhook-sent message shows the right label in the chat UI, not the generic "Bot" fallback unless `source_label` is genuinely absent).

**Blocked by:** 07.

**Status:** done

- [x] Confirm ticket 07's webhook endpoint sets `sender_id=None` and a non-null `source_label` on the persisted `Message`, matching what `groupMessages`' fallback assumes
- [x] Send a message through the real webhook endpoint and confirm it renders in `/conversas/:id` with the expected sender label (not the generic "Bot" fallback, unless `source_label` is genuinely absent)
- [x] If the shapes don't match (e.g. `source_label`'s format isn't a human-readable name), fix either the webhook payload/persistence or the frontend fallback so they agree
- [x] Tests: extend `messageGrouping.test.ts` and/or `Conversa.test.tsx` if the real shape reveals a case not currently covered
- [x] UI refactor: differentiate message colors in the chat screen by sender kind — current user, other user, and webhook/external sender should each be visually distinct (`frontend/src/routes/Conversa.tsx`)

## Comments

The first four items were resolved in an earlier pass (`224ccb2`, `a7c21f4`, `373863b`): `groupMessages` groups by `source_label` when `sender_id` is null, and the webhook → UI path was manually verified via `backend/insomnia/insomnia-webhook.json`.

This session closed the remaining item (sender-kind color differentiation), through two rounds of manual feedback:

- `groupMessages` (`frontend/src/lib/messageGrouping.ts`) now returns `senderKind: 'me' | 'other' | 'external'` per group, computed from `sender_id` vs. a `currentUserId` argument passed in from `Conversa.tsx` (via `getMe`, same pattern as `Sidebar.tsx`).
- First attempt used chat-bubble backgrounds + right-alignment for "me" — rejected by manual testing as ugly/not wanted.
- Final version (`frontend/src/routes/Conversa.tsx`): no bubbles, no alignment change, plain left-aligned text. Sender **name** color: mine → black (`text.primary`), other user → blue (`primary.main`), external/webhook → amber (`warning.dark`). Message **body** color: mine and other user → black, external/webhook → amber. External messages additionally show an info icon with a `Tooltip` — "Essa mensagem veio de um serviço externo" — styled in the same amber tone.
- TDD throughout: failing tests added first in `messageGrouping.test.ts` (senderKind cases) and `Conversa.test.tsx` (`data-sender-kind` attribute per bubble; external tooltip via `getByLabelText`), then implemented to green.
- Verified: `uv run pytest` (39/39), `npx vitest run` (42/42), `tsc --noEmit`, `oxlint`, `npm run build` all clean. Manually confirmed working in browser by the user.
- Not verified by the agent directly: no browser-automation tool was available in this session, so screenshots weren't taken by the agent — visual confirmation came from the user's own manual testing.
