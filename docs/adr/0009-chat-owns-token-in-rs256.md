# Chat has a token of its own, in RS256, and the service can never mint one

**Status:** accepted — **not yet implemented.** Tracked by
`.scratch/bwt-chat-microservice/issues/19-chat-token-signed-rs256.md`.

> **The service can still mint tokens today.** Ticket 01 took the chat token's
> *claims* — which is what the rest of the spec was blocked on — and deliberately
> left the signature alone: verification is HS256 against a shared secret. So the
> central guarantee below, that a compromised chat service cannot impersonate
> anyone, **is not true of the running code**. It becomes true when ticket 19
> lands, which must happen before this service sees production traffic. Everything
> else in this ADR describes the decision as accepted, not as shipped.


The service does not verify the product's access token. The monolith issues a
**chat token** of its own, from a dedicated endpoint, signed with RS256 and a key
id; the service validates it offline against the public key and never holds
material to mint any token at all. If the service is compromised, the attacker
cannot impersonate anyone — not in chat, not in the product.

## Why not reuse the product's token

The monolith signs its JWTs with HS256 using Django's own `SECRET_KEY`, which
also signs sessions and password resets. Verifying that token in chat would mean
sharing the key — and a symmetric key does not distinguish verifying from
signing.

The path that looked mandatory, then, was migrating the monolith's JWT settings
to RS256: a change that invalidates every token in circulation and demands a
coordinated rollout window of at least one access-token lifetime, affecting every
client of the monolith. It was expensive enough that we planned an interim step
in HS256 with a dedicated key, knowingly accepting that the service would remain
able to mint tokens the monolith accepts during the transition.

**None of that is necessary.** The chat token is a *new* token: the existing JWT
settings do not change, no token in circulation is invalidated, there is no
rollout window to coordinate. The debt the interim step would create buys
nothing, so it does not exist.

## The shape of the token

Short-lived — fifteen minutes, which makes it the revocation mechanism itself
(see [ADR-0011](0011-revocation-at-the-next-token.md)). It carries who the
requester is (identifier, company, user kind), what they may do (scopes,
including supervision, resolved in the monolith against a permission system the
service does not know), and enough to display them (name, avatar), which feeds
the identity projection without a single call.

**The audience claim is mandatory and verified.** It is what stops the product's
token being valid in chat and the chat token being valid in the product. Without
that check, having two tokens is worse than having one.

## Consequences

The public key lives in configuration, so the service boots with no network, and
the monolith's JWKS is consulted opportunistically for rotation, falling back to
the last known key. Publishing a new key id rotates the key with no redeploy of
the service; tokens signed with the previous one stay valid until they expire.

Two tokens now exist with different lifecycles, and every client has to know
which one goes where. That is the cost of not sharing a key, and it is smaller
than the alternative.

The issuing endpoint is the dependency this design creates in the monolith — and
it is the same machinery as the redemption described in
[ADR-0006](0006-session-handoff-via-exchange-code.md), so it is one thing to
learn, not two.
