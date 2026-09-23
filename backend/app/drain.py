"""The drain process: `drain_once` in a loop, and nothing else.

A separate process rather than a background task inside the API, for two
reasons that point the same way. In production, delivery that shares a process
with request handling dies with it and competes with it for the event loop. In
the test suite, a background tick would race every realtime assertion — the
whole point of `drain_once` being a callable is that a test can say *now* and
then assert, instead of waiting and hoping.

Failures are logged and retried rather than fatal. That is safe only because of
how `drain_once` orders its work: a row is marked after it is published, so a
Redis outage leaves every undelivered row pending and the backlog drains itself
when Redis returns. What such an outage moves is `oldest_unpublished_age`, which
is exactly the signal ticket 18 monitors — the failure is loud in the place
built to hear it.
"""

import asyncio
import logging

from app.db import async_session_maker
from app.services.outbox import drain_once

IDLE_SECONDS = 1.0

logger = logging.getLogger(__name__)


async def run_forever() -> None:
    """Drain until there is nothing left, then wait before asking again.

    Sleeping only on an empty tick is what keeps a backlog draining at full
    speed while an idle service stays cheap.
    """
    while True:
        try:
            async with async_session_maker() as session:
                published = await drain_once(session)
        except Exception:
            logger.exception("drain tick failed; pending rows stay pending")
            published = 0

        if published == 0:
            await asyncio.sleep(IDLE_SECONDS)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
