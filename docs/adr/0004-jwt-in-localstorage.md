# JWT stored in localStorage instead of an httpOnly cookie

**Status:** accepted

The frontend stores the JWT issued at login in `localStorage` and attaches it manually as `Authorization: Bearer <token>` on REST calls and as a query param on the WebSocket handshake. The alternative — an httpOnly cookie set by the backend — is the production-grade answer: it's immune to token theft via XSS, since JS on the page can never read it. We didn't take that path because it costs real backend work beyond this challenge's "simplified auth" scope: the backend would need to set/rotate the cookie, CORS would need `credentials: true` with an explicit origin allowlist, CSRF protection would become necessary (cookies auto-attach to requests, unlike a manually-attached bearer token), and the WebSocket handshake auth would change from "pass a token param" to "rely on the cookie being sent automatically."

Given the auth extra is meant to demonstrate a real JWT flow, not harden it against XSS, `localStorage` was accepted as a deliberate, documented trade-off rather than an oversight. With more time, moving to an httpOnly cookie would be the first hardening step.
