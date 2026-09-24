"""How far behind the identity projection is.

Its own module, and that is the whole reason for it: this read has no caller,
no token and therefore no Company, exactly like the drain's
`oldest_unpublished_age`. It has to read every Company's rows, so it cannot go
through `CompanyScope` — and `tests/test_company_isolation.py` exempts it *per
entity*, which it can only do per file. Leaving this function in
`services/identity.py` would mean exempting `UserProfile` there too, and
`profiles_by_user_id` in that same file is a read on behalf of a user that must
stay guarded. One function alone here is cheaper than a hole in that guard.
"""

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import UserProfile


async def projection_lag(db: AsyncSession) -> timedelta | None:
    """The widest gap between a source change and this service writing it.

    The projection's only health signal, because it has no miss path: nothing
    ever fetches an identity it does not hold, so a stopped event stream is
    invisible from inside. Every response keeps answering, promptly, with a
    name that is quietly months old — and the first report comes from a user,
    not from the service.

    The widest gap rather than an average, for the reason an average exists: it
    would hide the one user whose updates stopped arriving behind thousands
    that are fine.

    Rows with no `source_updated_at` are left out, and are not lag. They came
    from a composition command, which carries an identity but no timestamp to
    measure against; counting them as infinitely stale would peg the metric
    permanently at whatever the oldest Chat is.

    None means nothing is measurable yet, not that the projection is healthy.
    Whoever turns this into an alert has to say which one they mean.
    """
    return await db.scalar(
        select(func.max(UserProfile.synced_at - UserProfile.source_updated_at)).where(
            UserProfile.source_updated_at.is_not(None)
        )
    )
