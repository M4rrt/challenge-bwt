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

**Status:** ready-for-agent

- [ ] New `/webhook` route added to `App.tsx`, behind the existing auth guard
- [ ] Displays the current user's name and the required disclaimer text
- [ ] Form with conversation id, message body, sender name fields
- [ ] Submit computes the HMAC-SHA256 signature client-side (Web Crypto API) from `VITE_WEBHOOK_TEST_SECRET` and calls `POST /webhook/messages` with the `X-Signature` header
- [ ] Success and error responses are both shown as visible feedback on the page
- [ ] `VITE_WEBHOOK_TEST_SECRET` documented in the frontend env example / README
- [ ] Tests: submitting valid input shows success feedback (mocked fetch); a rejected/invalid response shows error feedback
