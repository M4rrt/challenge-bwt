# The chat domain is rewritten in FastAPI, not carried over from Django

**Status:** accepted

The service takes the **design** of the monolith's chat module — chat types,
message visibility, read state, supervision, cursor pagination, idempotency by
client message id — but rewritten in FastAPI and SQLAlchemy on top of the
backend this repository already has. The alternative was to carry the whole
Django app over, migrations and consumers included, into a slim
Django+Channels service.

## Considered Options

Carrying the Django app over would preserve code whose subtleties are documented
and tested, and would move the schema without translation. It was rejected in
order to reuse the WebSocket, the Redis fan-out and the Terraform infrastructure
this repository already has, rather than discarding them.

## Consequences

Every subtlety encoded in the source module has to be **re-derived**, not copied.
The one that worries most is documented there: a participant loaded through a
relation came back as the base `User` rather than the concrete subclass, and the
rule for who reads the staff-only thread answered "no" for an employee — failing
silently in both directions, sometimes dropping employees from their own fan-out,
sometimes keeping a client in it. That bug is re-introducible here and gets a
test before it gets code.

The source module never ran in production: it was a local prototype, well
documented, behind a feature flag. Its rules are reasonable hypotheses, not
behaviour validated by real traffic.
