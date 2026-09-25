"""One accepted socket, from the handshake to whichever close ends it.

A Chat connection is long-lived and its credential is not, and ADR-0011 chose to
reconcile those in band: the service warns shortly before expiry, the client
sends a new token over the same socket, and the service revalidates it. The
alternative — close and let them reconnect — costs a recovery query every
fifteen minutes and opens a window in which messages are lost.

**One task, one loop.** The receive and the three appointments are waited on
together rather than by a timer task per appointment. Two reasons, and they are
the whole shape of this module. A renewal moves two deadlines at once, so
separate tasks would have to agree on who cancels and re-arms whom. And every
branch here touches the database session and the address indexes, which are the
request's own and must not be used from two tasks at once — a lock would be the
alternative, and a loop needs none.

The pending receive is never cancelled to fire an appointment, only at teardown.
Cancelling a socket mid-`receive` is how a frame gets dropped between the
transport and the handler, which is exactly the loss in-band renewal exists to
avoid.

`core/connection_schedule.py` decides *when*; this decides *what*.
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone

from fastapi import WebSocket, WebSocketDisconnect

from app.core.chat_token import Caller, verify_chat_token
from app.core.close_codes import CloseCode
from app.core.connection_schedule import ConnectionSchedule, Due
from app.services.denylist import is_denied
from app.services.realtime import Address, Holder, close_quietly, connection_manager

RENEWAL_WARNING_LEAD = timedelta(seconds=60)
"""How long before expiry the client is told to go and fetch a new token.

Long enough to redeem a renewal credential against the monolith and come back
over a socket that is still open, and short enough that most of a fifteen-minute
token is spent not talking about tokens.
"""

REVALIDATION_INTERVAL = timedelta(seconds=60)
"""How often an open connection re-asks whether its holder still belongs here.

It bounds the window between a *write on this side* and the socket noticing at
one interval rather than at one token lifetime: a Participant removed whose
eviction never arrived, and a denylist entry that landed while nothing was
renewing.

**What it cannot do on its own is re-read a claim.** A deactivation and a lost
supervision scope live in the token, and the token does not change between
renewals — so re-running this predicate against the same `Caller` re-derives the
same answer, however often it runs. Those two are covered by the *renewal*
(the monolith issues the next token without the scope, or not at all) and, when a
lifetime is too long, by the denylist. ADR-0011 credits "revalidates periodically
and on every token renewal" with covering them, and it is the pair that does; the
periodic half alone covers what this service can see for itself.
"""

EXPIRING = "token.expiring"
"""Server → client: your credential is about to run out. Send a new one."""

RENEW = "token.renew"
"""Client → server: here is a new one, on this same connection."""

RENEWED = "token.renewed"
"""Server → client: accepted, revalidated, and this connection carries on."""


Authorise = Callable[[Caller], Awaitable[list[Address] | None]]
"""Where this caller may listen, or `None` if they may not listen at all.

One function asked at the handshake, at every renewal and at every revalidation,
so that entitlement has a single spelling. Returning the addresses rather than a
boolean is what makes a *changed* entitlement expressible: a Participant whose
role went from staff to client is still allowed in the Chat and no longer allowed
on its staff address, and a predicate could not say so.
"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def admit(websocket: WebSocket, token: str) -> Caller | None:
    """Who this socket belongs to, or nothing — having closed it with the right code.

    The handshake's two refusals about the credential itself, in one place
    because both sockets ask them: a token the service never accepted, and a
    token it has been told to stop accepting. Whether the *Chat* is theirs is a
    separate question, asked afterwards, and answered deliberately the same way
    as "no such Chat".
    """
    caller = verify_chat_token(token)
    if caller is None:
        await close_quietly(websocket, CloseCode.UNAUTHENTICATED)
        return None

    if await is_denied(caller, token):
        await close_quietly(websocket, CloseCode.ACCESS_REVOKED)
        return None

    return caller


class Connection:
    def __init__(
        self,
        websocket: WebSocket,
        *,
        caller: Caller,
        token: str,
        authorise: Authorise,
        chat_id: uuid.UUID | None = None,
    ) -> None:
        self._websocket = websocket
        self._caller = caller
        self._token = token
        self._authorise = authorise
        self._holder = Holder(caller.company_id, caller.id, chat_id)
        self._addresses: list[Address] = []
        self._schedule = ConnectionSchedule.starting(
            expires_at=caller.expires_at,
            now=_now(),
            warning_lead=RENEWAL_WARNING_LEAD,
            revalidation_interval=REVALIDATION_INTERVAL,
        )

    async def serve(self, addresses: list[Address]) -> None:
        """Join the addresses, run until something ends it, leave them.

        The caller has already accepted the socket and decided the addresses,
        because both belong to the handshake: a socket that may not be here is
        refused before it is accepted.
        """
        self._addresses = addresses
        connection_manager.connect(addresses, self._websocket, self._holder)
        try:
            await self._run()
        except WebSocketDisconnect:
            pass
        finally:
            connection_manager.disconnect(self._addresses, self._websocket, self._holder)

    async def _run(self) -> None:
        receiving = asyncio.create_task(self._websocket.receive_json())
        try:
            while True:
                due, wait = self._schedule.due_next(_now())
                done, _ = await asyncio.wait({receiving}, timeout=wait)
                if receiving not in done:
                    if not await self._keep(due):
                        return
                    continue

                frame = receiving.result()
                if not await self._received(frame):
                    return
                receiving = asyncio.create_task(self._websocket.receive_json())
        finally:
            receiving.cancel()

    async def _keep(self, due: Due) -> bool:
        """Carry out the appointment that came due. False means this connection is over."""
        match due:
            case Due.WARN_OF_EXPIRY:
                await self._websocket.send_json(
                    {"type": EXPIRING, "expires_at": self._caller.expires_at.isoformat()}
                )
                self._schedule.done(due, _now())
                return True
            case Due.CLOSE_EXPIRED:
                await close_quietly(self._websocket, CloseCode.TOKEN_EXPIRED)
                return False
            case Due.REVALIDATE:
                self._schedule.done(due, _now())
                return await self._still_allowed()

    async def _still_allowed(self) -> bool:
        """Re-ask where this caller may listen, and move the socket to that answer.

        Asked on every renewal and on every revalidation, which is the one place
        an already-open connection can learn that something changed underneath
        it. On a renewal it is asked about a *new* `Caller`, so it sees changed
        claims too; on a periodic tick the claims are the ones it already had, and
        what can have moved is this side — the Participant row and the denylist.
        A caller who may no longer be here is closed as `ACCESS_REVOKED`
        rather than left to the deadline: their credential is fine and this Chat
        is not theirs, and a client told to renew would renew and come straight
        back.

        The denylist is asked first and on the same schedule, so the exceptional
        revocation gets the same bounded window as the ordinary one instead of a
        path of its own.

        A caller who may still be here but is entitled to fewer addresses — the
        Participant whose role went from staff to client — simply stops listening
        on the one they lost. That was ticket 07's open gap: the staff address was
        joined at a handshake that nothing ever revisited. It is the renewal that
        catches that one, `user_kind` being a claim: the periodic tick would ask
        about the same claims it already had.
        """
        if await is_denied(self._caller, self._token):
            await close_quietly(self._websocket, CloseCode.ACCESS_REVOKED)
            return False

        addresses = await self._authorise(self._caller)
        if addresses is None:
            await close_quietly(self._websocket, CloseCode.ACCESS_REVOKED)
            return False

        if addresses != self._addresses:
            # Leave and rejoin rather than diff: the indexes are keyed by
            # channel, no frame can be delivered between two statements of one
            # task, and a diff is a third place entitlement could be decided.
            connection_manager.disconnect(self._addresses, self._websocket, self._holder)
            connection_manager.connect(addresses, self._websocket, self._holder)
            self._addresses = addresses
        return True

    async def _received(self, frame: object) -> bool:
        """Handle a client frame. An unnamed or unknown one is ignored, as it always was.

        Anything that is not a JSON object is ignored rather than raising. A frame
        from the wire is whatever the client sent, and a list where an object was
        expected should not be able to take a connection down.
        """
        if not isinstance(frame, dict):
            return True

        if frame.get("type") == RENEW:
            offered = frame.get("token")
            return await self._renew(offered if isinstance(offered, str) else None)
        return True

    async def _renew(self, token: str | None) -> bool:
        """Take a new credential for the connection already open on this socket.

        The new token has to name the same person in the same Company. A socket
        is joined to its addresses for whoever opened it, so accepting a token
        for somebody else would hand one person's fan-out to another — and the
        addresses were decided at a handshake that is over.

        A renewal that fails to verify is `UNAUTHENTICATED` rather than the
        deadline quietly arriving: the client has just been told to renew, and
        "the token you sent is not one I accept" is a different instruction to it
        than "renew".
        """
        renewed = verify_chat_token(token) if token is not None else None
        if (
            token is None
            or renewed is None
            or renewed.id != self._caller.id
            or renewed.company_id != self._caller.company_id
        ):
            await close_quietly(self._websocket, CloseCode.UNAUTHENTICATED)
            return False

        self._caller = renewed
        self._token = token
        self._schedule.renewed(renewed.expires_at)
        if not await self._still_allowed():
            return False

        await self._websocket.send_json(
            {"type": RENEWED, "expires_at": renewed.expires_at.isoformat()}
        )
        return True
