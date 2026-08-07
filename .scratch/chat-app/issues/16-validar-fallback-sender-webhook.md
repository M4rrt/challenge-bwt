# 16 — Validar fallback de remetente do webhook contra a implementação real da 07

**What to build:** Ticket 10 implements the chat screen's sender-fallback for messages with `sender_id: null` as `source_label ?? 'Bot'` (`frontend/src/lib/messageGrouping.ts`), written ahead of ticket 07 (webhook ingestion) actually existing, based only on the `MessageRead` schema shape. Once 07 is implemented, verify the webhook path actually produces `sender_id: null` + a populated `source_label` as assumed, and that the fallback reads correctly end-to-end (a webhook-sent message shows the right label in the chat UI, not the generic "Bot" fallback unless `source_label` is genuinely absent).

**Blocked by:** 07.

**Status:** ready-for-agent

- [ ] Confirm ticket 07's webhook endpoint sets `sender_id=None` and a non-null `source_label` on the persisted `Message`, matching what `groupMessages`' fallback assumes
- [ ] Send a message through the real webhook endpoint and confirm it renders in `/conversas/:id` with the expected sender label (not the generic "Bot" fallback, unless `source_label` is genuinely absent)
- [ ] If the shapes don't match (e.g. `source_label`'s format isn't a human-readable name), fix either the webhook payload/persistence or the frontend fallback so they agree
- [ ] Tests: extend `messageGrouping.test.ts` and/or `Conversa.test.tsx` if the real shape reveals a case not currently covered
- [ ] UI refactor: differentiate message colors in the chat screen by sender kind — current user, other user, and webhook/external sender should each be visually distinct (`frontend/src/routes/Conversa.tsx`)
