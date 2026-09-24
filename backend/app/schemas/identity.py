import uuid

from pydantic import AwareDatetime, BaseModel


class IdentitySnapshot(BaseModel):
    """One identity as the monolith last knew it, and when it last knew it.

    A snapshot carrying no verb. Creation, change, deactivation and
    anonymisation are the four things the monolith's identity stream reports,
    and all four are the same write here, because a projection stores what is
    true now and every response reads exactly that. Storing the verb would
    store something nothing ever reads — and deciding what "anonymised" means
    would put a data-protection policy, and its wording, inside a chat service
    that has no business holding either. The monolith anonymises and sends the
    name it wants shown.

    `source_updated_at` is by the *monolith's* clock and is the whole ordering
    rule: these arrive at-least-once and out of order, and it is what stops a
    late redelivery reinstating a name that has since been replaced. It is
    required here, unlike on the profile row, where null means the row came
    from a composition command that carried no timestamp at all.

    It must carry a zone. A naive timestamp does not say which clock it came
    from: stored into a `timestamptz` column it is read as the database
    server's zone, shifting it by hours and silently reordering events against
    each other, and compared in Python against an aware one it raises, turning
    a whole bulk load into a 500. `AwareDatetime` refuses it at the door, which
    is the only answer that cannot be wrong later — the monolith is told to fix
    its emitter while the projection is still correct.
    """

    user_id: uuid.UUID
    company_id: uuid.UUID
    user_kind: str
    display_name: str
    avatar_url: str | None = None
    source_updated_at: AwareDatetime


class IdentityEvent(IdentitySnapshot):
    """A snapshot as the event stream delivers it, one user at a time.

    `event_id` identifies the delivery rather than the identity, and the
    service stores no record of having seen it. Deduplication by event id would
    be a second mechanism for something `source_updated_at` already settles:
    a redelivered event carries the timestamp it carried the first time, the
    comparison in `apply_identities` is strict, and an equal timestamp loses —
    so a replay writes nothing whether it arrives once or ten times, in any
    order, interleaved with anything.

    It stays required on the wire because it is what makes a replay legible in
    a log, and because the moment this ingress grows work that is not
    idempotent by construction — an outbox row on the way out, which is ticket
    15 — the timestamp stops covering it and a table of seen ids becomes
    load-bearing. That table belongs to that work, not to this one.
    """

    event_id: uuid.UUID


class IdentityBulkLoad(BaseModel):
    """Initial population and rebuild: what is true for a set of users at once.

    Not an event, and deliberately not shaped like a batch of them. A rebuild
    is not a sequence of things that happened; it is the monolith restating the
    present, which is why there is no event id here to explain the absence of.
    """

    identities: list[IdentitySnapshot]
