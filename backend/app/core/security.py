import hashlib
import hmac

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.chat_token import Caller, verify_chat_token
from app.core.config import settings

bearer_scheme = HTTPBearer(auto_error=False)


def verify_webhook_signature(body: bytes, signature: str | None) -> bool:
    if not signature:
        return False
    expected = hmac.new(settings.webhook_hmac_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


async def get_current_caller(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Caller:
    caller = verify_chat_token(credentials.credentials) if credentials else None
    if caller is None:
        raise HTTPException(status_code=401, detail="invalid or missing token")
    return caller
