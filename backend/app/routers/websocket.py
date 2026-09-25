"""The two sockets, and what the handshake settles before either is accepted.

Entitlement is decided by `_where_they_may_listen` below and by nothing else. It
runs at the handshake, at every in-band renewal and at every periodic
revalidation, so a connection cannot outlive the permission that opened it —
which was the gap ticket 07 left behind: a Participant whose role changed stayed
on the staff address for the rest of that connection's life.
"""

import uuid

from fastapi import APIRouter, Depends, WebSocket
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chat_token import Caller
from app.core.close_codes import CloseCode
from app.core.company_scope import CompanyScope
from app.core.message_visibility import may_read
from app.db import get_db
from app.models.message import MessageVisibility
from app.services.connection import Authorise, Connection, admit
from app.services.message import ChatNotFoundError, chat_of_participant
from app.services.realtime import (
    Address,
    address_for_chat,
    address_for_chat_staff,
    address_for_user,
)

router = APIRouter(prefix="/websocket", tags=["websocket"])


def _where_they_may_listen(db: AsyncSession, chat_id: uuid.UUID) -> Authorise:
    """The Chat's addresses for this caller, or nothing if the Chat is not theirs.

    The staff address is joined here or not at all. Entitlement is decided by the
    same predicate the API asks — so there is no per-frame filter for a future
    emitter to forget — and it is decided again on every renewal and
    revalidation, so a role that changed under an open socket is honoured rather
    than waited out.
    """

    async def authorise(caller: Caller) -> list[Address] | None:
        try:
            chat = await chat_of_participant(db, CompanyScope.of(caller), chat_id, caller.id)
        except ChatNotFoundError:
            return None

        addresses = [address_for_chat(caller.company_id, chat_id)]
        if may_read(
            reader_kind=caller.user_kind,
            reader_company_id=caller.company_id,
            chat_company_id=chat.company_id,
            chat_type=chat.type,
            visibility=MessageVisibility.STAFF_ONLY,
        ):
            addresses.append(address_for_chat_staff(caller.company_id, chat_id))
        return addresses

    return authorise


async def _own_address(caller: Caller) -> list[Address] | None:
    """A user's own socket has nothing to authorise beyond the token itself.

    It carries what is computed for one person rather than what belongs to a
    Chat, so there is no membership to lose. What can still take it away is the
    denylist, which `Connection` checks on the same schedule.
    """
    return [address_for_user(caller.company_id, caller.id)]


@router.websocket("/chats/{chat_id}")
async def chat_socket(
    websocket: WebSocket,
    chat_id: uuid.UUID,
    token: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    caller = await admit(websocket, token)
    if caller is None:
        return

    authorise = _where_they_may_listen(db, chat_id)
    addresses = await authorise(caller)
    if addresses is None:
        await websocket.close(code=CloseCode.UNAUTHENTICATED)
        return

    await websocket.accept()
    await Connection(
        websocket, caller=caller, token=token, authorise=authorise, chat_id=chat_id
    ).serve(addresses)


@router.websocket("/users/me")
async def user_socket(websocket: WebSocket, token: str) -> None:
    caller = await admit(websocket, token)
    if caller is None:
        return

    await websocket.accept()
    await Connection(websocket, caller=caller, token=token, authorise=_own_address).serve(
        [address_for_user(caller.company_id, caller.id)]
    )
