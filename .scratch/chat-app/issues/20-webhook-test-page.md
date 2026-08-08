# 20 — WebHook test page (UI)

**What to build:** A new `/webhook` route, reachable from the "Usar webHook" link added in ticket 19, that lets a logged-in user manually exercise the existing `POST /webhook/messages` backend endpoint (see `backend/app/routers/webhook.py`) from the browser.

Layout follows the same pattern established for the conversas screen in ticket 19 (large lateral spacing, centered content column).

Contents:
- The name of the currently logged-in user (via the existing `getMe`/auth context).
- A disclaimer: "essa é apenas uma pagina para teste do WebHook".
- Form fields: conversation id, message body, sender name (maps to the backend's `source_label`).
- A submit button that calls `POST /webhook/messages`.
- Feedback area showing the result of the test call (success with the created message, or the error returned).

**Signature handling:** the backend requires an `X-Signature` header — HMAC-SHA256 of the raw request body, keyed with `webhook_hmac_secret` (`backend/app/core/config.py:12`). The signature is computed client-side using a secret read from a Vite env var (`VITE_WEBHOOK_TEST_SECRET`), which must be set to match the backend's configured `webhook_hmac_secret` in whatever environment this runs against. Do not commit a real secret value — document the env var in the frontend README/`.env.example` instead. See `docs/adr/0005-client-side-hmac-webhook-test-page.md` for why this is test-page-only and must not be replicated in a real deploy.

**Blocked by:** 19 (reuses its layout pattern; is the target of its "Usar webHook" link).

**Status:** done

- [x] New `/webhook` route added to `App.tsx`, behind the existing auth guard
- [x] Displays the current user's name and the required disclaimer text
- [x] Form with conversation id, message body, sender name fields
- [x] Submit computes the HMAC-SHA256 signature client-side (Web Crypto API) from `VITE_WEBHOOK_TEST_SECRET` and calls `POST /webhook/messages` with the `X-Signature` header
- [x] Success and error responses are both shown as visible feedback on the page
- [x] `VITE_WEBHOOK_TEST_SECRET` documented in the frontend env example / README
- [x] Tests: submitting valid input shows success feedback (mocked fetch); a rejected/invalid response shows error feedback

## Comments

Ticket 19 (the shared "large lateral spacing, centered column" layout and the "Usar webHook" link pointing here) hadn't been implemented yet when this ticket was picked up. Per explicit direction, this page ships its own centered-column MUI layout instead of waiting on/reusing a nonexistent ticket-19 component; the "Usar webHook" link itself remains ticket 19's responsibility.

`sendWebhookMessage` (`frontend/src/lib/api.ts`) posts the exact pre-serialized JSON string used for signing — not a re-serialized object — so the signed bytes and the sent bytes can never drift. `signWebhookBody` (`frontend/src/lib/webhookSignature.ts`) uses the Web Crypto API and was verified byte-for-byte against Python's `hmac.new(...).hexdigest()`, matching the backend's `verify_webhook_signature`.

Code review (Standards + Spec axes) caught two spec gaps, fixed in a follow-up commit: success feedback originally showed only the message id/timestamp instead of the full created message, and a missing `VITE_WEBHOOK_TEST_SECRET` silently produced a bad signature surfaced as a confusing 401 instead of a clear config error.

Verified: `tsc -b`, `oxlint`, `npx vitest run` (50/50) all clean. No browser-automation tool was available in this session, so the agent didn't take screenshots — manual verification against the real backend was done by the user.
