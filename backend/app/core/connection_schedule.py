"""What a live connection is waiting for next, and for how long.

A WebSocket that renews in band has three appointments rather than one: warn
the client shortly before the credential expires, close the connection if the
renewal never came, and re-ask whether the holder is still allowed to be here.
They are not independent — a renewal moves two of them and re-arms the first —
so which one comes next is a question worth answering in one place.

It is arithmetic over a `now` the caller supplies, with no clock, no socket and
no session in it. That is deliberate: the alternative is three sleeping tasks
per connection, which cannot be asserted about without sleeping and which have
to agree on who cancels whom when a token is renewed.

`ConnectionSchedule` says *when*; `services/connection.py` decides *what to do*.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


class Due(StrEnum):
    """The three appointments, and the whole set of them."""

    WARN_OF_EXPIRY = "warn_of_expiry"
    CLOSE_EXPIRED = "close_expired"
    REVALIDATE = "revalidate"


@dataclass
class ConnectionSchedule:
    """Mutable on purpose: a renewal is a connection changing its own deadlines."""

    expires_at: datetime
    revalidate_at: datetime
    warning_lead: timedelta
    revalidation_interval: timedelta
    warned: bool = False

    @classmethod
    def starting(
        cls,
        *,
        expires_at: datetime,
        now: datetime,
        warning_lead: timedelta,
        revalidation_interval: timedelta,
    ) -> "ConnectionSchedule":
        return cls(
            expires_at=expires_at,
            revalidate_at=now + revalidation_interval,
            warning_lead=warning_lead,
            revalidation_interval=revalidation_interval,
        )

    def due_next(self, now: datetime) -> tuple[Due, float]:
        """The soonest appointment, and the seconds to wait for it.

        Never negative. A token minted with less life left than the warning lead
        is a token whose warning is already overdue, and the honest answer to
        "how long until it" is none at all rather than a wait in the past.

        The close is always a candidate, even before the warning has been
        given. The deadline is a backstop for a renewal that never arrives, and
        a backstop conditional on the warning having been delivered would be no
        backstop at all — a client that never reads its socket would keep the
        connection forever.
        """
        appointments = [(Due.REVALIDATE, self.revalidate_at), (Due.CLOSE_EXPIRED, self.expires_at)]
        if not self.warned:
            appointments.append((Due.WARN_OF_EXPIRY, self.expires_at - self.warning_lead))

        due, moment = min(appointments, key=lambda appointment: appointment[1])
        return due, max(0.0, (moment - now).total_seconds())

    def done(self, due: Due, now: datetime) -> None:
        """Record that what was due has been carried out.

        The warning is once per token, so it is struck off rather than
        rescheduled; revalidation is forever, so it moves an interval on.
        `CLOSE_EXPIRED` is never reported here — carrying it out ends the
        connection, and there is no schedule left to tell.
        """
        if due is Due.WARN_OF_EXPIRY:
            self.warned = True
        elif due is Due.REVALIDATE:
            self.revalidate_at = now + self.revalidation_interval

    def renewed(self, expires_at: datetime) -> None:
        """A new credential: a later deadline, and a warning owed again.

        Re-arming the warning is the half that is easy to forget. A connection
        renewed once and never warned again would run to its second expiry in
        silence and close, which is the exact failure in-band renewal exists to
        avoid.
        """
        self.expires_at = expires_at
        self.warned = False
