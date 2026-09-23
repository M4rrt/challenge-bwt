from fastapi import APIRouter, Depends

from app.core.chat_token import Caller
from app.core.security import get_current_caller
from app.schemas.caller import CallerRead

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=CallerRead)
async def me(caller: Caller = Depends(get_current_caller)) -> CallerRead:
    return CallerRead(
        id=caller.id,
        company_id=caller.company_id,
        user_kind=caller.user_kind,
        scopes=list(caller.scopes),
        display_name=caller.display_name,
        avatar_url=caller.avatar_url,
    )
