import hashlib
import hmac

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db import get_db
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


async def decode_user_from_token(token: str, db: AsyncSession) -> User | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None

    user_id = payload.get("sub")
    if user_id is None:
        return None

    return await db.scalar(select(User).where(User.id == user_id))


def verify_webhook_signature(body: bytes, signature: str | None) -> bool:
    if not signature:
        return False
    expected = hmac.new(settings.webhook_hmac_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await decode_user_from_token(token, db)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid or missing token")
    return user
