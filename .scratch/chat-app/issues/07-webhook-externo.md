# 07 — Webhook externo

**What to build:** An external system can POST a message into an existing Conversation, HMAC-signed, and it's delivered live to participants exactly like a user-sent message. The mandatory webhook requirement, with the security-validation piece explicitly called out.

**Blocked by:** 06.

**Status:** ready-for-agent

- [ ] `POST /webhook/messages` — payload includes `conversation_id` + body; HMAC signature verified (`X-Signature` header, `hmac.compare_digest`) before any DB lookup
- [ ] Invalid/missing signature → 401, before touching the database
- [ ] Valid signature → persists a `Message` with `sender_type="external"` and a `source_label`, using ticket 05's persistence path
- [ ] Delivered live via ticket 06's WebSocket/Redis path to the conversation's connected participants
- [ ] Tests: valid signature accepted and delivered live, tampered body rejected, invalid `conversation_id` rejected, isolation still holds (only that conversation's participants receive it)
