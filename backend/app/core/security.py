import hashlib
import hmac
import uuid

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.acting_user import ActingUser
from app.core.chat_token import Caller, verify_chat_token
from app.core.company_scope import CompanyScope
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


async def get_company_scope(caller: Caller = Depends(get_current_caller)) -> CompanyScope:
    """The caller's Company, injected rather than derived at each call site.

    A router that builds its own scope is a router that can build the wrong one.
    """
    return CompanyScope.of(caller)


async def get_acting_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    acting_user_id: str | None = Header(default=None, alias="X-Acting-User"),
    acting_company_id: str | None = Header(default=None, alias="X-Acting-Company"),
) -> ActingUser:
    """The authority behind a composition command: the monolith, acting for someone.

    Both halves are required and neither defaults. The credential is compared
    whole, in constant time, and it is not a chat token: a chat token presented
    here fails the comparison, and this credential presented to a public route
    is not a JWT and never becomes a Caller. The two vocabularies of "who is
    calling" stay separate on purpose.
    """
    if credentials is None or not hmac.compare_digest(
        credentials.credentials, settings.internal_service_token
    ):
        raise HTTPException(status_code=401, detail="invalid or missing service credential")

    if acting_user_id is None or acting_company_id is None:
        raise HTTPException(status_code=401, detail="no acting user named")

    try:
        return ActingUser(
            id=uuid.UUID(acting_user_id), company_id=uuid.UUID(acting_company_id)
        )
    except ValueError:
        raise HTTPException(status_code=401, detail="acting user is not an identifier") from None


async def get_command_scope(acting: ActingUser = Depends(get_acting_user)) -> CompanyScope:
    """The Company a command writes into, taken from the user it acts for."""
    return CompanyScope.of(acting)
