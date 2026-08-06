from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db import get_db
from app.models.user import User
from app.schemas.user import UserSummary
from app.services.user import list_users

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserSummary])
async def list_all(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[UserSummary]:
    users = await list_users(db)
    return [UserSummary.model_validate(user) for user in users]
