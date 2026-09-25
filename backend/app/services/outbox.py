"""Writing a delivery down, and paying it afterwards.

The request writes rows; a separate drain publishes them. Splitting the two
buys both halves of the same guarantee: nobody is told about a Message a
rollback will erase, and nothing is lost if the process dies between the commit
and the publish.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outbox import OutboxEvent
from app.schemas.eviction import Eviction
from app.services.realtime import Address, address_for_control, publish

DEFAULT_BATCH = 100


def enqueue(db: AsyncSession, address: Address, payload: str) -> None:
    """Add a delivery to the caller's open transaction. It does not commit.

    Not committing is the whole contract: the row has to land or not land with
    whatever the caller is also writing, and a commit here would let an
    announcement outlive the Message it announces.
    """
    db.add(
        OutboxEvent(
            company_id=address.company_id, address=address.channel, payload=payload
        )
    )


def enqueue_eviction(
    db: AsyncSession,
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    chat_id: uuid.UUID | None = None,
) -> None:
    """Close this person's connections, in one Chat or in all of them.

    Spelled once, because two callers write this row for different reasons — a
    Participant removed, and a credential revoked — and an address built twice is
    an address that can be built two ways.

    `chat_id` narrows it to the one Chat; leaving it out means every connection
    they hold. Like every other `enqueue`, it does not commit: the caller decides
    what this row has to land or not land with.
    """
    enqueue(
        db,
        address_for_control(company_id),
        Eviction(company_id=company_id, user_id=user_id, chat_id=chat_id).model_dump_json(),
    )


async def drain_once(db: AsyncSession, limit: int = DEFAULT_BATCH) -> int:
    """Publish the pending batch once and return how many went out.

    This is seam 2. Tests call it between sending and asserting; the production
    process calls it in a loop. One callable for both is deliberate — a drain
    that could only be observed by waiting for a background task would make
    every realtime test a race.

    Each row is published and then marked, one commit at a time. The order
    matters and is the at-least-once choice: dying after the publish and before
    the mark redelivers that row on the next run, while marking first would drop
    it silently. A duplicate frame is visible and can be deduplicated by message
    id; a dropped one is neither.

    **One row per transaction, taken with `FOR UPDATE SKIP LOCKED`.** That is
    what makes the drain safe to run as more than one replica: a row another
    drain already holds is skipped rather than waited for, so two replicas share
    the backlog instead of publishing all of it twice. Locking the whole batch
    instead would not do — the first commit releases every lock in the
    transaction, leaving the rest of the batch unguarded while it is still being
    processed.

    Oldest first, which is the order rows were *inserted*. That is not a
    guarantee about the order things happened: `created_at` is stamped at insert,
    so a slow transaction can commit after a faster one that started later, and
    its row will still sort first. Within a single send it holds, because the
    message and everything announcing it are inserted together.
    """
    published = 0
    while published < limit:
        event = await db.scalar(
            select(OutboxEvent)
            .where(OutboxEvent.published_at.is_(None))
            .order_by(OutboxEvent.created_at, OutboxEvent.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if event is None:
            break

        await publish(event.address, event.payload)
        event.published_at = datetime.now(timezone.utc)
        await db.commit()
        published += 1
    return published


async def oldest_unpublished_age(db: AsyncSession) -> timedelta | None:
    """How far behind the drain is, or None when it owes nothing.

    The realtime health signal. It is an age rather than a count because a
    thousand rows written a second ago is a busy service and one row written ten
    minutes ago is a drain that has stopped, and a count cannot tell those
    apart.
    """
    oldest = await db.scalar(
        select(func.min(OutboxEvent.created_at)).where(OutboxEvent.published_at.is_(None))
    )
    if oldest is None:
        return None
    return datetime.now(timezone.utc) - oldest
