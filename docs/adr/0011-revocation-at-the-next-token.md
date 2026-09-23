# Revocation takes effect at the next token, and the connection does not drop to renew

**Status:** accepted

The source module required a revoked permission to block the **next action**, and
so re-read participation and permission from the database on every request. With
company, user kind and scopes travelling as claims of a chat token the service
neither mints nor revokes, that requirement changes shape: **the short TTL
becomes the revocation mechanism**. A permission removed, a user deactivated or a
company switched off stop applying at the next token request — with no
distributed revocation list and with the service asking nobody anything.

**This contradicts, in writing, the source module's docstring.** Anyone reading
that module and then this service will find the rule inverted; it is deliberate,
and the cost was accepted in exchange for chat not consulting the monolith on
every request.

## The WebSocket renews in band, but has a deadline

An expiring token cannot mean reconnecting: reconnecting costs a recovery query
and opens a window in which messages are lost. Shortly before expiry the service
warns the connection; the client obtains a new token and sends it over that same
connection; the service revalidates the token **and the Chat's authorisation**
and confirms. That is the moment revocation actually happens — the monolith
simply does not issue the next token, or issues it without the scope.

The deadline still exists as a backstop: if the refresh does not arrive by
expiry, the connection closes with a dedicated *token expired* code, distinct
from the unauthenticated one. The distinction matters so the client knows to
renew and reconnect rather than send the user to a login screen.

Having both is the point. The deadline alone costs a recovery every fifteen
minutes; in-band renewal alone creates a path where forgetting to reschedule the
deadline leaves a connection alive forever — and that defect is silent.

## Whoever loses access leaves the Chat

Authorising only at connect time means removing a Participant announces it to the
Chat but evicts nobody: until they reconnect, that person keeps receiving
messages. The service indexes its connections by Chat **and by user**, so a
removal closes that user's connections in that Chat with a dedicated *access
revoked* code — the token stays valid for everything else. Beyond that, every
Chat connection revalidates authorisation periodically and on every token
renewal, which covers losing the supervision scope and being deactivated, not
just explicit removal.

For the exceptional cases where fifteen minutes is too long — a dismissal, a ban
— an event from the monolith puts the token or the user on a short-lived denylist
whose entries expire with the token they block, and closes that user's
connections. It is the exception path, not the normal one.

## Consequences

The maximum window between "the monolith decided you may not" and "the service
stops letting you" is the token's TTL, with no shared state and no replicated
list. Composition — the operation where stale data would hurt most — does not
depend on that window: it is validated in the monolith, against live data, before
the command leaves ([ADR-0010](0010-no-request-depends-on-the-monolith.md)).

On the client side this requires distinguishing three closures that cannot be
treated alike: token expired (renew and reconnect), access revoked (leave the
Chat, do not retry) and network failure (exponential backoff). Treating them all
as failure turns every expiry into a growing wait; treating them all as expiry
makes the client hammer a Chat it was removed from.
