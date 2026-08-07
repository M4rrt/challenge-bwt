# Webhook test page computes the HMAC signature client-side

**Status:** accepted

The `/webhook` test page (ticket 20, `.scratch/chat-app/issues/20-webhook-test-page.md`) lets a logged-in user manually exercise `POST /webhook/messages` from the browser. That endpoint requires an `X-Signature` header — HMAC-SHA256 of the raw request body, keyed with `webhook_hmac_secret` (`backend/app/core/config.py:12`). To let the page sign requests, the secret is read from a frontend build-time env var (`VITE_WEBHOOK_TEST_SECRET`) and the signature is computed in-browser with the Web Crypto API.

This means the secret ships in the frontend bundle and is readable by anyone with devtools access to the page. That is only acceptable because the page exists purely as a manual test tool for this challenge, is guarded behind the app's own login, and says so explicitly via an on-page disclaimer ("essa é apenas uma pagina para teste do WebHook"). It is **not** a pattern to carry into a real deployment: a production integration would sign server-side (either the real external sender owns the secret and never exposes it, or the test page proxies through an authenticated backend endpoint that signs on its behalf and never returns the secret to the client).

With more time, this would be replaced with a proper API key integration: each external caller gets its own issued key, the backend validates and scopes access per key (and can revoke individual keys without rotating a shared secret), and no signing secret is ever shipped to a browser.
