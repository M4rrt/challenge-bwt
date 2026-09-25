"""Test-side minting of chat tokens.

The monolith is the only issuer of a chat token; tests stand in for it, minting
tokens with the same secret and the same claim shape the service verifies.

The signature algorithm is deliberately still HS256 — swapping it for RS256 with
a key id and a JWKS is a separate, pre-production piece of work. What this helper
fixes now is the *claims* contract, which that swap does not change.
"""

import uuid
from datetime import datetime, timedelta, timezone

from jose import jwt

from app.core.chat_token import CHAT_CLAIM_NAMESPACE, Caller
from app.core.config import settings

# Callers share a Company unless a test names another one, so that crossing the
# boundary is always something a test did on purpose.
DEFAULT_COMPANY_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


class _Omitted:
    """A claim the monolith did not issue at all, as opposed to one left at its default."""


OMITTED = _Omitted()


def mint_chat_token(
    *,
    user_id: uuid.UUID | str | None = None,
    company_id: uuid.UUID | str | _Omitted | None = None,
    user_kind: str = "staff",
    scopes: list[str] | None = None,
    display_name: str = "Ana Souza",
    avatar_url: str | None = None,
    audience: str | None = None,
    expires_in: timedelta | None = timedelta(minutes=15),
    secret: str | None = None,
) -> str:
    chat_claims: dict[str, object] = {
        "user_kind": user_kind,
        "scopes": scopes if scopes is not None else ["chat:read", "chat:write"],
        "display_name": display_name,
        "avatar_url": avatar_url,
    }
    if not isinstance(company_id, _Omitted):
        chat_claims["company_id"] = str(company_id or DEFAULT_COMPANY_ID)

    claims: dict[str, object] = {
        "sub": str(user_id or uuid.uuid4()),
        CHAT_CLAIM_NAMESPACE: chat_claims,
    }
    if audience is not None:
        claims["aud"] = audience
    if expires_in is not None:
        claims["exp"] = datetime.now(timezone.utc) + expires_in

    return jwt.encode(claims, secret or settings.jwt_secret_key, algorithm="HS256")


def caller_token(user_id: uuid.UUID | None = None, **claims: object) -> tuple[str, str]:
    """A caller's identifier and a chat token carrying it, as the monolith would issue."""
    user_id = user_id or uuid.uuid4()
    return str(user_id), mint_chat_token(user_id=user_id, **claims)  # type: ignore[arg-type]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def make_caller(
    user_id: uuid.UUID | None = None,
    *,
    company_id: uuid.UUID | None = None,
    user_kind: str = "staff",
    scopes: tuple[str, ...] = ("chat:read", "chat:write"),
    display_name: str = "Ana Souza",
    avatar_url: str | None = None,
    expires_in: timedelta = timedelta(minutes=15),
) -> Caller:
    return Caller(
        id=user_id or uuid.uuid4(),
        company_id=company_id or DEFAULT_COMPANY_ID,
        user_kind=user_kind,
        scopes=scopes,
        display_name=display_name,
        avatar_url=avatar_url,
        expires_at=datetime.now(timezone.utc) + expires_in,
    )
