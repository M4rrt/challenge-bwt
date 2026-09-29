"""The chat token: the only thing the service knows about who is calling.

Every claim the service acts on travels in the token the monolith issued. There
is no lookup behind it — the service holds no user table to look anything up in.

Verification is RS256 against a public key selected by `kid`. The service
holds no signing material at all, only the public half of whatever the
monolith publishes (`app/services/chat_token_keys.py` keeps that current), so
a compromise of this service cannot mint a token it would itself accept —
that guarantee is ADR-0009 in full.

The claims contract is fixed independently of the signature: `sub` and `exp`
are registered claims, everything chat-specific is namespaced under
`CHAT_CLAIM_NAMESPACE`.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from jose import JWTError, jwt

from app.core.config import settings

CHAT_CLAIM_NAMESPACE = "https://brwinetours.com/chat"

SUPERVISION_SCOPE = "chat:supervise"
"""The claim that makes a caller a Supervisor, carried as a scope and not a third user kind.

Ticket 13's own note: `may_read` (`core/message_visibility.py`) classifies a
reader by `ParticipantRole(reader_kind)`, whose members are exactly
`staff | client`. Reusing that predicate for a Supervisor rather than opening a
bypass for them only works if the monolith keeps issuing an ordinary
`user_kind` and adds supervision on top of it here — a token claiming
`user_kind: "supervisor"` would fall into the default-deny branch and read
nothing, which is the loud failure the design prefers to a leak.
"""


@dataclass(frozen=True)
class Caller:
    """Who is calling, and until when.

    `expires_at` is a claim like the others, not bookkeeping: ADR-0011 makes the
    lifetime the revocation mechanism, so the moment it ends is the moment the
    service stops believing any of the rest. A long-lived WebSocket has to
    schedule against it — warn, then close — which a decode that merely *checked*
    `exp` and threw it away could not support.
    """

    id: uuid.UUID
    company_id: uuid.UUID
    user_kind: str
    scopes: tuple[str, ...]
    display_name: str | None
    avatar_url: str | None
    expires_at: datetime


def is_supervisor(caller: Caller) -> bool:
    """Whether this caller may read their Company's Chats without being a Participant.

    One predicate over the one claim that grants it, asked wherever a read path
    needs to choose between a Participant's own Chats and the whole Company's —
    so there is one spelling of "is this caller a Supervisor" and not one per
    call site.
    """
    return SUPERVISION_SCOPE in caller.scopes


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
            expires_at=datetime.fromtimestamp(claims["exp"], timezone.utc),  # type: ignore[arg-type]
        )
    except (KeyError, TypeError, ValueError):
        return None


def _index_by_kid(keys: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    """A list of JWKS keys, indexed by `kid`. A key with no `kid` cannot be selected, so it is dropped."""
    return {key["kid"]: key for key in keys if isinstance(key, dict) and "kid" in key}


def _parse_keyset(jwks_json: str) -> dict[str, dict[str, object]]:
    """A JWKS document, indexed by `kid`."""
    try:
        document = json.loads(jwks_json)
        keys = document["keys"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return {}
    return _index_by_kid(keys)


_bootstrap_keyset = _parse_keyset(settings.chat_token_jwks)
"""What the service was configured with — always available, so it boots with no network."""

_active_keyset: dict[str, dict[str, object]] = dict(_bootstrap_keyset)
"""What the service currently verifies against.

`app/services/chat_token_keys.py` is the only writer, and only replaces this
wholesale on a successful JWKS URL fetch: a rotated-out `kid` stops working, a
failed fetch leaves whatever was here before untouched, and until the first
fetch ever succeeds this is exactly `_bootstrap_keyset`.
"""


def set_active_keyset(keys: list[dict[str, object]]) -> None:
    """Replace the active keyset with a successful fetch's keys.

    A fetch that came back with no usable keys — `{"keys": []}`, or a
    document with only key-less entries — is not "roll back to boot": that
    would silently re-trust a `kid` the monolith may have since revoked. It
    leaves whatever was active untouched, same as a failed fetch does one
    layer up in `app/services/chat_token_keys.py`.
    """
    indexed = _index_by_kid(keys)
    if indexed:
        global _active_keyset
        _active_keyset = indexed


def verify_chat_token(token: str) -> Caller | None:
    """The claims, or nothing — and `exp` is one of the claims it requires.

    The library only enforces an `exp` it finds, so a token issued without one
    would be accepted forever. That is not a token this service can revoke, and
    revocation-by-expiry is the whole of ADR-0011, so the missing claim is a
    refusal rather than a token with no deadline to schedule against.

    `alg` is checked twice on purpose. The explicit check here closes the
    classic algorithm-confusion attack — a caller who controls their own
    header asking for `alg: none`, or for an algorithm this service never
    agreed to — before a `kid` lookup ever runs; `algorithms=["RS256"]` below
    is `jwt.decode`'s own copy of the same rule, kept because the two checks
    are cheap and nothing should depend on either alone.
    """
    try:
        header = jwt.get_unverified_header(token)
    except JWTError:
        return None

    if header.get("alg") != "RS256":
        return None

    key = _active_keyset.get(header.get("kid"))
    if key is None:
        return None

    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=settings.chat_token_audience,
            issuer=settings.chat_token_issuer,
            options={"require_aud": True},
        )
    except JWTError:
        return None

    return _caller_from(claims)
