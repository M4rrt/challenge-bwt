"""Mint a chat token for manual testing, standing in for the monolith.

The service has no login: the monolith is the only issuer of a chat token, so
there is no request a developer can make to obtain one. This is what fills that
gap for Insomnia and curl — the same secret and the same claim shape the service
verifies, which is also what `tests/chat_tokens.py` does for the suite.

    uv run python -m scripts.mint_chat_token                  # one staff caller
    uv run python -m scripts.mint_chat_token --kind client    # an end client
    uv run python -m scripts.mint_chat_token --insomnia       # a whole fixture set

NOT A PRODUCTION TOOL, and it cannot become one: it works only because the
service still verifies HS256 against a shared secret, which is the property
ADR-0009 exists to remove. When ticket 19 lands RS256, this script needs the
test private key and the service will hold only the public half — which is the
point, and this file is one of the places that will have to say so.
"""

import argparse
import json
import uuid
from datetime import datetime, timedelta, timezone

from jose import jwt

from app.core.chat_token import CHAT_CLAIM_NAMESPACE
from app.core.config import settings

DEFAULT_COMPANY_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
"""One Company unless a caller names another, so crossing the boundary is deliberate.

The same constant the test suite uses, for the same reason: a fixture set that
shared no Company by default would make every isolation check pass by accident.
"""


def mint(
    *,
    user_id: uuid.UUID,
    company_id: uuid.UUID,
    user_kind: str,
    display_name: str,
    minutes: int,
) -> str:
    claims = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=minutes),
        CHAT_CLAIM_NAMESPACE: {
            "company_id": str(company_id),
            "user_kind": user_kind,
            "scopes": ["chat:read", "chat:write"],
            "display_name": display_name,
            "avatar_url": None,
        },
    }
    return jwt.encode(claims, settings.jwt_secret_key, algorithm="HS256")


_FIXTURES = (
    ("a", "Ana Souza", "staff"),
    ("b", "Beto Lima", "staff"),
    ("c", "Carla Dias", "staff"),
    ("d", "Davi Rocha", "staff"),
    ("e", "Elena Cliente", "client"),
)
"""The cast the Insomnia collections are written around.

D is never put in a Chat — they exist so that "sees nothing" is asserted by
somebody real rather than by an empty database. E is the end client, so the
Staff-only Message has somebody to be kept from.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", type=uuid.UUID, default=None)
    parser.add_argument("--company-id", type=uuid.UUID, default=DEFAULT_COMPANY_ID)
    parser.add_argument("--kind", default="staff", choices=("staff", "client"))
    parser.add_argument("--name", default="Ana Souza")
    parser.add_argument("--minutes", type=int, default=720)
    parser.add_argument(
        "--insomnia",
        action="store_true",
        help="print the whole fixture set as the environment block to paste",
    )
    args = parser.parse_args()

    if not args.insomnia:
        print(
            mint(
                user_id=args.user_id or uuid.uuid4(),
                company_id=args.company_id,
                user_kind=args.kind,
                display_name=args.name,
                minutes=args.minutes,
            )
        )
        return

    environment: dict[str, str] = {
        "base_url": "http://localhost:8000",
        "ws_base_url": "ws://localhost:8000",
        "service_token": settings.internal_service_token,
        "company_id": str(args.company_id),
        "chat_id": "",
        "client_chat_id": "",
        "message_id": "",
        "cursor": "",
    }
    for letter, name, kind in _FIXTURES:
        user_id = uuid.uuid4()
        environment[f"user_{letter}_id"] = str(user_id)
        environment[f"token_{letter}"] = mint(
            user_id=user_id,
            company_id=args.company_id,
            user_kind=kind,
            display_name=name,
            minutes=args.minutes,
        )
    print(json.dumps(environment, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
