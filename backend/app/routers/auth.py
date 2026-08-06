from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db import get_db
from app.models.user import User
from app.schemas.user import Token, UserCreate, UserLogin, UserRead
from app.services.auth import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    UsernameAlreadyRegisteredError,
    login_user,
    register_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=201)
async def register(data: UserCreate, db: AsyncSession = Depends(get_db)) -> UserRead:
    try:
        user = await register_user(db, data)
    except EmailAlreadyRegisteredError:
        raise HTTPException(status_code=409, detail="email already registered")
    except UsernameAlreadyRegisteredError:
        raise HTTPException(status_code=409, detail="username already registered")
    return UserRead.model_validate(user)


@router.post("/login", response_model=Token)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)) -> Token:
    try:
        access_token = await login_user(db, data)
    except InvalidCredentialsError:
        raise HTTPException(status_code=401, detail="invalid credentials")
    return Token(access_token=access_token)


@router.get("/me", response_model=UserRead)
async def me(current_user: User = Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(current_user)
