# Session handed to the chat interface via an exchange code

**Status:** accepted

The chat interface is an application of its own, on its own domain, and
therefore has no session with the monolith. The BWT app redirects to it with a
**single-use, short-lived exchange code** in the URL fragment; the interface
redeems it in a POST to the monolith and receives, in return, a **renewal
credential scoped to chat** — not the product's session. With it, it asks for
fifteen-minute chat tokens ([ADR-0009](0009-chat-owns-token-in-rs256.md)) for as
long as the session lasts.

## The credential's scope is the point

Redeeming the product's access/refresh pair would make the chat interface carry
a credential valid across the whole of BWT. A chat-scoped credential only ever
buys a chat token, and a chat token is only valid where its audience says it is.
It is the same reasoning as the audience claim, carried all the way to the front
door: whatever leaks from the chat interface compromises chat, never the
product.

## The redemption response also says where the service lives

Redemption returns, alongside the credential, the API and WebSocket URLs. The
client learns the chat's address **from the monolith** rather than having it
compiled into an environment variable — which makes it possible to move the
service, or switch it off, without shipping a new version of any client. That
matters most for the native apps, which consume the same service and cannot be
updated on demand.

## Considered Options

- **The token itself in the fragment**: rejected. With the chat token living
  minutes, the fragment would have to carry something durable, and what is
  durable in the monolith today is a 365-day refresh with no rotation.
- **`httpOnly` cookie on the parent domain**: still good protection for the web
  client and adoptable later, but no longer "the destination" — it does not
  generalise to a native app, and chat has more clients than the web.
- **Full OIDC authorization flow**: rejected along with the decision that the
  service only verifies signatures, with no OIDC provider.
- **A login screen in the chat interface**: rejected for requiring a second
  login.

## Consequences

The code is useless after redemption and expires in seconds, so what stays in
browser history is worthless. What remains in the interface is the chat
credential, in JavaScript-accessible storage — the same trade-off as
[ADR-0004](0004-jwt-in-localstorage.md), now with a far smaller blast radius.

The chat module embedded in the BWT frontend is **removed**, and its place
becomes a link out that carries the code. Keeping both would mean two web chat
interfaces against one contract, and the second one always falls behind.
