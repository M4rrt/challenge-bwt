"""The three moments a live connection is waiting for, and which comes first.

Pulled out of the socket because it is arithmetic, and arithmetic asserted
through a WebSocket is asserted by sleeping. Everything here is a pure function
of a `now` the test chooses.
"""

from datetime import datetime, timedelta, timezone

from app.core.connection_schedule import ConnectionSchedule, Due

NOW = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)
LEAD = timedelta(seconds=60)
# Long enough to stay out of the way: a test about the warning should not have
# to reason about revalidation falling first, which at production numbers it
# does. The one test that is about that sets its own.
INTERVAL = timedelta(hours=1)


def schedule(*, expires_in: timedelta = timedelta(minutes=15), now: datetime = NOW):
    return ConnectionSchedule.starting(
        expires_at=now + expires_in,
        now=now,
        warning_lead=LEAD,
        revalidation_interval=INTERVAL,
    )


def test_the_warning_falls_one_lead_before_the_expiry():
    due, wait = schedule(expires_in=timedelta(minutes=15)).due_next(NOW)

    assert due is Due.WARN_OF_EXPIRY
    assert wait == (timedelta(minutes=15) - LEAD).total_seconds()


def test_revalidation_comes_first_when_it_falls_before_the_warning():
    """Which it does at production numbers: the warning is a fresh token's last appointment."""
    early = ConnectionSchedule.starting(
        expires_at=NOW + timedelta(minutes=15),
        now=NOW,
        warning_lead=LEAD,
        revalidation_interval=timedelta(seconds=10),
    )

    assert early.due_next(NOW) == (Due.REVALIDATE, 10.0)


def test_the_expiry_is_what_remains_once_the_warning_has_been_given():
    """The warning is given once per token; the close is what the schedule then waits for."""
    given = schedule(expires_in=timedelta(seconds=30))
    given.done(Due.WARN_OF_EXPIRY, NOW)

    due, wait = given.due_next(NOW)

    assert due is Due.CLOSE_EXPIRED
    assert wait == 30.0


def test_a_moment_already_past_is_due_with_no_wait():
    """A token minted with less life than the lead is warned about at once, not late."""
    already = schedule(expires_in=timedelta(seconds=5))

    due, wait = already.due_next(NOW)

    assert (due, wait) == (Due.WARN_OF_EXPIRY, 0.0)


def test_revalidating_puts_the_next_one_an_interval_away():
    walked = ConnectionSchedule.starting(
        expires_at=NOW + timedelta(minutes=15),
        now=NOW,
        warning_lead=LEAD,
        revalidation_interval=timedelta(seconds=10),
    )
    later = NOW + timedelta(seconds=10)

    walked.done(Due.REVALIDATE, later)

    assert walked.due_next(later) == (Due.REVALIDATE, 10.0)


def test_renewing_moves_the_warning_and_the_close_and_arms_the_warning_again():
    """A renewed connection is warned again before the *new* expiry, not silently never."""
    renewed = schedule(expires_in=timedelta(seconds=30))
    renewed.done(Due.WARN_OF_EXPIRY, NOW)

    renewed.renewed(expires_at=NOW + timedelta(minutes=15))

    assert renewed.due_next(NOW) == (Due.WARN_OF_EXPIRY, 840.0)
