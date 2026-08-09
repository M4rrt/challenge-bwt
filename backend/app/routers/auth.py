from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db import get_db
from app.models.user import User
from app.schemas.user import AccessToken, RefreshRequest, Token, UserCreate, UserLogin, UserRead
from app.services.auth import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    UsernameAlreadyRegisteredError,
    login_user,
    refresh_access_token,
    register_user,
    revoke_refresh_token,
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
        access_token, refresh_token = await login_user(db, data)
    except InvalidCredentialsError:
        raise HTTPException(status_code=401, detail="invalid credentials")
    return Token(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=AccessToken)
async def refresh(data: RefreshRequest, db: AsyncSession = Depends(get_db)) -> AccessToken:
    try:
        access_token = await refresh_access_token(db, data.refresh_token)
    except InvalidRefreshTokenError:
        raise HTTPException(status_code=401, detail="invalid refresh token")
    return AccessToken(access_token=access_token)


@router.post("/logout", status_code=204)
async def logout(data: RefreshRequest, db: AsyncSession = Depends(get_db)) -> None:
    await revoke_refresh_token(db, data.refresh_token)


@router.get("/me", response_model=UserRead)
async def me(current_user: User = Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(current_user)
