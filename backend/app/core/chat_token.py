"""The chat token: the only thing the service knows about who is calling.

Every claim the service acts on travels in the token the monolith issued. There
is no lookup behind it — the service holds no user table to look anything up in.

NOT PRODUCTION READY. Verification is still HS256 against a shared secret, which
means this service holds material that can MINT a token it would itself accept.
ADR-0009 exists precisely to remove that property: under RS256 the service holds
only a public key and cannot sign anything. Until ticket 19 lands, a compromise
of this service is a compromise of every chat identity, and the ADR describes a
guarantee the code does not yet provide.

Ticket 19 replaces this module's `verify_chat_token` with RS256 + `kid` + JWKS
and a mandatory `aud` check. The claims contract below does not change.
"""

import uuid
from dataclasses import dataclass

from jose import JWTError, jwt

from app.core.config import settings

CHAT_CLAIM_NAMESPACE = "https://brwinetours.com/chat"


@dataclass(frozen=True)
class Caller:
    id: uuid.UUID
    company_id: uuid.UUID
    user_kind: str
    scopes: tuple[str, ...]
    display_name: str | None
    avatar_url: str | None


def _caller_from(claims: dict[str, object]) -> Caller | None:
    chat_claims = claims.get(CHAT_CLAIM_NAMESPACE)
    if not isinstance(chat_claims, dict):
        return None

    try:
        return Caller(
            id=uuid.UUID(claims["sub"]),
            company_id=uuid.UUID(chat_claims["company_id"]),
            user_kind=chat_claims["user_kind"],
            scopes=tuple(chat_claims["scopes"]),
            display_name=chat_claims.get("display_name"),
            avatar_url=chat_claims.get("avatar_url"),
        )
    except (KeyError, TypeError, ValueError):
        return None


def verify_chat_token(token: str) -> Caller | None:
    try:
        claims = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None

    return _caller_from(claims)
