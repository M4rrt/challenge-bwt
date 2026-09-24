"""The internal ingress: commands the monolith sends, for what it is the authority on.

Authenticated by a service credential, and requiring headers naming the user the
monolith is acting for — a command that names nobody is refused, because there
is no Chat without an author (ADR-0010).

These are meant to be unreachable from the public internet as well, and today
they are not: the deployed ALB forwards every path to the same target group, so
the credential is the only lock. Closing that is ticket 18, together with the
ingress the monolith will actually come in by — blocking the public path first
would leave composition with no way in at all. `infra/README.md` says the same
where somebody changing the listener would be looking.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.acting_user import ActingUser
from app.core.company_scope import CompanyScope
from app.core.security import get_acting_user, get_command_scope, require_service_credential
from app.db import get_db
from app.schemas.chat import AddParticipantCommand, ChatCommand, ChatComposed
from app.schemas.identity import IdentityBulkLoad, IdentityEvent
from app.services.chat import (
    ChatNotFoundError,
    ChatShapeError,
    ParticipantNotFoundError,
    add_participant,
    create_chat,
    remove_participant,
)
from app.services.identity import apply_identities

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/chats", response_model=ChatComposed, status_code=201)
async def create(
    command: ChatCommand,
    acting: ActingUser = Depends(get_acting_user),
    scope: CompanyScope = Depends(get_command_scope),
    db: AsyncSession = Depends(get_db),
) -> ChatComposed:
    try:
        chat = await create_chat(db, scope, acting, command)
    except ChatShapeError as refused:
        raise HTTPException(status_code=422, detail=refused.detail)
    return ChatComposed.of(chat)


@router.post("/chats/{chat_id}/participants", response_model=ChatComposed)
async def add(
    chat_id: uuid.UUID,
    command: AddParticipantCommand,
    scope: CompanyScope = Depends(get_command_scope),
    db: AsyncSession = Depends(get_db),
) -> ChatComposed:
    try:
        chat = await add_participant(db, scope, chat_id, command)
    except ChatNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")
    except ChatShapeError as refused:
        raise HTTPException(status_code=422, detail=refused.detail)
    return ChatComposed.of(chat)


@router.delete("/chats/{chat_id}/participants/{user_id}", response_model=ChatComposed)
async def remove(
    chat_id: uuid.UUID,
    user_id: uuid.UUID,
    scope: CompanyScope = Depends(get_command_scope),
    db: AsyncSession = Depends(get_db),
) -> ChatComposed:
    try:
        chat = await remove_participant(db, scope, chat_id, user_id)
    except (ChatNotFoundError, ParticipantNotFoundError):
        raise HTTPException(status_code=404, detail="participant not found")
    return ChatComposed.of(chat)


@router.post("/identity-events", status_code=204)
async def receive_identity_event(
    event: IdentityEvent,
    _: None = Depends(require_service_credential),
    db: AsyncSession = Depends(get_db),
) -> None:
    """The identity stream, arriving over the same ingress as commands.

    A broker was the alternative and is deferred: it would add a second test
    seam for no behaviour this spec needs. This route is a thin adapter over
    `apply_event`, so putting a broker in front of it later touches nothing in
    the domain.

    No acting-user header, unlike the commands above. A composition names an
    author because there is no Chat without one; a user's name changing in the
    monolith has no author to name, and demanding one would be asking the
    monolith to invent it. The Company comes from the event itself, which is
    the same shape the webhook already has — the payload names the boundary it
    writes into, and every read of it goes back through `CompanyScope`.

    204, whether the event was applied, lost to a newer one, or had already
    been seen. At-least-once means the sender retries on a failure and must not
    be told anything it would act on differently.
    """
    await apply_identities(db, [event])


@router.post("/identities", status_code=204)
async def load_identities(
    load: IdentityBulkLoad,
    _: None = Depends(require_service_credential),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Initial population and rebuild, over the same write as the event stream.

    A new environment starts with an empty projection and a corrupted one has
    to be refillable, and neither is a reason to replay the whole identity
    history. What arrives here is dated like an event, so a rebuild racing the
    live stream loses to anything the stream has already delivered that is
    newer — the two cannot fight.
    """
    await apply_identities(db, load.identities)
