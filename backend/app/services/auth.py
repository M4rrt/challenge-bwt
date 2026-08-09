import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.user import UserCreate, UserLogin


class EmailAlreadyRegisteredError(Exception):
    pass


class UsernameAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class InvalidRefreshTokenError(Exception):
    pass


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed_password.encode())


def create_access_token(user_id: str) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expires_minutes)
    payload = {"sub": user_id, "exp": expires_at}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


async def create_refresh_token(db: AsyncSession, user_id: str) -> str:
    raw_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expires_days)
    db.add(
        RefreshToken(user_id=user_id, token_hash=hash_refresh_token(raw_token), expires_at=expires_at)
    )
    await db.commit()
    return raw_token


async def register_user(db: AsyncSession, data: UserCreate) -> User:
    existing_email = await db.scalar(select(User).where(User.email == data.email))
    if existing_email is not None:
        raise EmailAlreadyRegisteredError(data.email)

    existing_username = await db.scalar(select(User).where(User.username == data.username))
    if existing_username is not None:
        raise UsernameAlreadyRegisteredError(data.username)

    user = User(
        email=data.email, username=data.username, hashed_password=hash_password(data.password)
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def login_user(db: AsyncSession, data: UserLogin) -> tuple[str, str]:
    user = await db.scalar(select(User).where(User.email == data.email))
    if user is None or not verify_password(data.password, user.hashed_password):
        raise InvalidCredentialsError()

    access_token = create_access_token(str(user.id))
    refresh_token = await create_refresh_token(db, str(user.id))
    return access_token, refresh_token


async def _find_refresh_token(db: AsyncSession, raw_refresh_token: str) -> RefreshToken | None:
    token_hash = hash_refresh_token(raw_refresh_token)
    return await db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))


async def refresh_access_token(db: AsyncSession, raw_refresh_token: str | None) -> str:
    if raw_refresh_token is None:
        raise InvalidRefreshTokenError()

    refresh_token = await _find_refresh_token(db, raw_refresh_token)
    now = datetime.now(timezone.utc)
    if (
        refresh_token is None
        or refresh_token.revoked_at is not None
        or refresh_token.expires_at < now
    ):
        raise InvalidRefreshTokenError()

    return create_access_token(str(refresh_token.user_id))


async def revoke_refresh_token(db: AsyncSession, raw_refresh_token: str | None) -> None:
    if raw_refresh_token is None:
        return

    refresh_token = await _find_refresh_token(db, raw_refresh_token)
    if refresh_token is not None and refresh_token.revoked_at is None:
        refresh_token.revoked_at = datetime.now(timezone.utc)
        await db.commit()
