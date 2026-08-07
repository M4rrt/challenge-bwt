# 07 — Webhook externo

**What to build:** An external system can POST a message into an existing Conversation, HMAC-signed, and it's delivered live to participants exactly like a user-sent message. The mandatory webhook requirement, with the security-validation piece explicitly called out.

**Blocked by:** 06.

**Status:** done

- [x] `POST /webhook/messages` — payload includes `conversation_id` + body; HMAC signature verified (`X-Signature` header, `hmac.compare_digest`) before any DB lookup
- [x] Invalid/missing signature → 401, before touching the database
- [x] Valid signature → persists a `Message` with `sender_type="external"` and a `source_label`, using ticket 05's persistence path
- [x] Delivered live via ticket 06's WebSocket/Redis path to the conversation's connected participants
- [x] Tests: valid signature accepted and delivered live, tampered body rejected, invalid `conversation_id` rejected, isolation still holds (only that conversation's participants receive it)

## Comments

Implemented on `worktree-ticket-07-webhook-externo`. Signature covers the raw request body bytes (HMAC-SHA256, hex-encoded), verified in `app/core/security.py::verify_webhook_signature` before the router touches the DB or parses the payload. `conversation_id` is checked for existence only (`assert_conversation_exists`), not participant membership — the webhook caller isn't a participant, and the HMAC secret is the trust boundary. Persistence reuses a `_persist_and_publish` helper shared with ticket 05's `send_message`, extracted in `app/services/message.py`. Automated tests: 6 cases in `backend/tests/test_webhook.py`, full backend suite (39 tests) green.

Manually verified via `backend/insomnia/insomnia-webhook.json` (all 6 requests, including a UTF-8 `source_label` case). Manual testing surfaced a real bug: two webhook messages with different `source_label`s (both `sender_id: null`) rendered under the same sender label in the chat UI, because `groupMessages` (ticket 10) grouped purely by `sender_id`. Root-caused and fixed on `worktree-ticket-16-fallback-sender-webhook` (see ticket 16) — not a defect in this ticket's own scope, but a gap in ticket 10's grouping logic that this ticket's real traffic exposed.

Deferred (see `docs/decisions.md`): replay protection (no timestamp/nonce) and a safe way for an external system to discover which `conversation_id` to use. Request shape and signing recipe documented in `backend/README.md`'s "Webhook" section.
