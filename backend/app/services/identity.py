"""The identity projection's writes and its one read.

Inbound writes feed it and nothing else does, because there is no miss path:
nothing here ever fetches an identity it does not have. A name the projection
has never been told is simply absent from the response, which is the honest
answer and not a reason to call the monolith (ADR-0010).

Every write is idempotent, because every one of them arrives at-least-once. The
identity inside a composition command carries no `source_updated_at` — that is
the wire shape ticket 05 fixed, and landing this projection must not move it —
so it takes the only reading left open to it: an identity of unknown age is the
oldest there is, so it creates the row when nobody has said anything about the
user and never overwrites what something dated already said.
"""

import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy import func, or_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.company_scope import CompanyScope
from app.models.identity import UserProfile
from app.schemas.chat import ParticipantIdentity
from app.schemas.identity import IdentitySnapshot

_CONFLICT_TARGET = ("company_id", "user_id")
"""The unique constraint every write upserts against, named once.

Three writes land on this table and each one has to name the same conflict
target; spelled per call site, a fourth would be one edit away from silently
inserting a duplicate profile instead of updating the one that is there.
"""


async def profiles_by_user_id(
    db: AsyncSession, scope: CompanyScope, user_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, UserProfile]:
    """The profiles of these users, as a lookup a response can be built from.

    In bulk rather than one at a time: a page of messages from twenty senders
    is one query, not twenty, and a caller resolving them row by row is how a
    list endpoint acquires a query per message without anybody noticing.
    """
    wanted = set(user_ids)
    if not wanted:
        return {}

    result = await db.scalars(
        scope.select(UserProfile).where(UserProfile.user_id.in_(wanted))
    )
    return {profile.user_id: profile for profile in result.all()}


async def remember_identities(
    db: AsyncSession, scope: CompanyScope, identities: Iterable[ParticipantIdentity]
) -> None:
    """The composition command's write: create what is missing, overwrite nothing.

    It does not commit, for the same reason `enqueue` does not — the profile has
    to land in the same transaction as the composition that carried it, so a
    refused command leaves no trace of the people it named.

    `ON CONFLICT DO NOTHING` is the whole of the idempotency and the whole of
    the ordering rule at once. The command has no `source_updated_at` to
    compare, so it must lose to anything already stored: a command redelivered
    from last week would otherwise reinstate a name the event stream has since
    replaced, and reinstating a replaced name is the one failure this projection
    exists to prevent.
    """
    rows = [
        {
            "id": uuid.uuid4(),
            "company_id": scope.company_id,
            "user_id": identity.user_id,
            "user_kind": identity.user_kind.value,
            "display_name": identity.display_name,
            "avatar_url": identity.avatar_url,
        }
        for identity in identities
    ]
    if not rows:
        return

    await db.execute(
        insert(UserProfile)
        .values(rows)
        .on_conflict_do_nothing(index_elements=list(_CONFLICT_TARGET))
    )


def _newest_per_user(
    snapshots: Sequence[IdentitySnapshot],
) -> list[IdentitySnapshot]:
    """One snapshot per (Company, user), keeping the newest the batch carries.

    Postgres refuses to let a single `ON CONFLICT DO UPDATE` touch the same row
    twice, and a rebuild is the one write that plausibly carries a user more
    than once — two pages stitched together, or a user changed while the export
    ran. Left alone that is not a dropped row, it is the whole load failing.

    Resolved by the same rule the database applies between statements, so the
    batch cannot disagree with itself about what "newest" means depending on
    whether two snapshots happened to arrive together.
    """
    newest: dict[tuple[uuid.UUID, uuid.UUID], IdentitySnapshot] = {}
    for snapshot in snapshots:
        key = (snapshot.company_id, snapshot.user_id)
        seen = newest.get(key)
        if seen is None or snapshot.source_updated_at > seen.source_updated_at:
            newest[key] = snapshot
    return list(newest.values())


async def apply_identities(
    db: AsyncSession, snapshots: Sequence[IdentitySnapshot]
) -> None:
    """The dated writes — the event stream and the bulk load — in one function.

    Both say the same thing, "this is who this user is, as of then", so both
    land the same way and the ordering rule cannot come apart between them. An
    event is one snapshot and a rebuild is many; that is the only difference,
    and it is the routes' difference, not this one's.

    Last-writer-wins by `source_updated_at`, compared in the database rather
    than read-then-write, so two events for the same user racing on two workers
    cannot both read the old row and both decide they are newer.

    The `WHERE` on the conflict is the whole ordering rule, and the whole of
    the idempotency too. Without it an event redelivered days late would
    reinstate the name it carried — the failure this projection exists to
    prevent, and one that shows up as a user whose old name comes back for no
    reason anybody can reproduce. The comparison is strict, so a redelivery of
    the current row's own event writes nothing. A null `source_updated_at`
    loses, because it means the row came from a composition command that
    carried no timestamp, and anything dated is newer than something undated.

    `synced_at` is set here explicitly, and the column carries no `onupdate` to
    do it — that fires for ORM updates, and every write to this table is a Core
    upsert. Leaning on it would freeze the lag metric at the row's creation
    time, reporting a projection that is perfectly fresh precisely when it has
    stopped being written to.
    """
    if not snapshots:
        return

    statement = insert(UserProfile).values(
        [
            {
                "id": uuid.uuid4(),
                "company_id": snapshot.company_id,
                "user_id": snapshot.user_id,
                "user_kind": snapshot.user_kind,
                "display_name": snapshot.display_name,
                "avatar_url": snapshot.avatar_url,
                "source_updated_at": snapshot.source_updated_at,
            }
            for snapshot in _newest_per_user(snapshots)
        ]
    )
    await db.execute(
        statement.on_conflict_do_update(
            index_elements=list(_CONFLICT_TARGET),
            set_={
                "user_kind": statement.excluded.user_kind,
                "display_name": statement.excluded.display_name,
                "avatar_url": statement.excluded.avatar_url,
                "source_updated_at": statement.excluded.source_updated_at,
                "synced_at": func.clock_timestamp(),
            },
            where=or_(
                UserProfile.source_updated_at.is_(None),
                UserProfile.source_updated_at < statement.excluded.source_updated_at,
            ),
        )
    )
    await db.commit()
