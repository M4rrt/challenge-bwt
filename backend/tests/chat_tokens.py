"""Test-side minting of chat tokens.

The monolith is the only issuer of a chat token; tests stand in for it,
minting tokens with a fixed RSA key pair and the same claim shape the service
verifies. The public half of `TEST_KEY_PAIR` is what `CHAT_TOKEN_JWKS` in
`.env`/`.env.example` holds — the service verifies against a public key from
configuration exactly as it would in production, only the config points at a
throwaway key made for tests.

Both key pairs below are fixed, not regenerated per run: `CHAT_TOKEN_JWKS` in
`.env`/`.env.example` is a static file and has to hold the public half that
matches whatever `TEST_KEY_PAIR` signs with. Neither key protects anything —
they exist only so a test can mint a token the way the monolith would.
"""

import base64
import json
import uuid
from dataclasses import dataclass
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


@dataclass(frozen=True)
class _KeyPair:
    kid: str
    private_pem: str
    public_jwk: dict[str, object]


# The key the service is configured to trust — its public half, verbatim, is
# what CHAT_TOKEN_JWKS in .env/.env.example holds.
TEST_KEY_PAIR = _KeyPair(
    kid="test-chat-key-1",
    private_pem="""-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDTrlybm/D4DlCD
xu+fVol5v2NE/X05QM20k//5veXd7YjfpMyQJLojxeK/9KCRfarjFxpz/376PLrJ
rcqMcdpoNcy5MJNwKnJFRr2PxTKt+5aXBhQh6yp8PovzKNjqjFLBmq0OBndHzBzf
nrrVQxdYbI2kD9I+L5Xolc5T9OcugAk/G6ucYoEIEbRJI13/67U5+H6++WUjG++V
hEuTbMDMMAZmTbOInqjgQqCauJMR2NLYfVjqp+ZmAyzu7wDgneia8wNDthsSMXSo
u4OQcEy2tF2lVW276LtB7ZddfJpWhXGoYD4mCMduTcmsRLD+ng7xEiVq8YRzsJXz
4Ik9CcZDAgMBAAECggEABf0CxawtrvbItFGmab2K+hS9/C+noT0CFL+zGB+VJygX
HSyOVO2VDnoEpiWHfVYuxWnb57gsoWuiZR4zgrGd2iDbf8muAhhRT0BnEHAltOJP
KkqTuznp48XpM6HOMSRzGuMDTkhEi5Vso67b3jidqnS3tRJ1gijads/2HE3rVFdh
tFf62GLpKS3nyYN0CihhqUhaww2eFVZ7Gkejitgj4NI11GPKLYXwPxHFZSFVeO0w
1C/+wwp2qK283Ngtp9n6LN86W/aaHKGWEa7Lj1y6Uhfb+Ym50X7+hoXUI/LHSwm0
5XpAJPHRo2eApDoCoIPGTWdQRTv9Ga60EVGHmh94AQKBgQD8xvmaBGfbqvNl4YVZ
VsGg/zhPIqTAxMAJ6uN/56VtnniL7ZYgX1ctHDqT2brMfJ9RJ44GFToBMC4nG7QF
yQjj+x75Tmot8laywlN1rqOup7vp6ubAbViTDA3CVwZZeBLGtBk78IOWOsEiFFQ6
MjVICRxN+2lzL/ceY/fscAygQwKBgQDWYUFjApxDCdjbU4/+6kenMVvvEjLLLNk2
eevvgUs6vmmC8xu+D5SQVqt44k5UxOigJ5HZu5PFS1FboWC+4pwxzBih9SnywOW1
BX5AZcOMRVlf7ZAuYYGEg7PUx6WU2MlkGAUPBgahbfAQ2QXi+wZZ777uSAFBXJsf
vYfUW1biAQKBgQDJGtSCAHdQgNVcfOvGhAtQtzxpWTqSUvYl7cZJgFZQu/9T9BW4
c6G7tfW0o0jGX2+w9TM9C642O8q8OoIjCCoWlzexSP2YyHDJj2ku+14mGjSaidRD
y7roYnKf5vSaQblOdQKOeW93Gg+FuX65PjC9uuHV+OuQRNzqRMZ+STcCWQKBgA+2
6VgcpN+1JRROt8tz2PTEhXys1NRX4URBA652x9DyjEFxGKOB+N3rvH4L+Ln2BSdY
PzS6r0ZTEw+ocLMNYW21DEky83Q795qhYHPQAdmSa87AV0VPGHNiRBhg2h5jFcAk
kppbUrkamfJiNjBBPmHxVQmadZ0Y8LYO6poCaAgBAoGADA+aw6nbGW+hlxGR5j68
ghIQo4L1Ttp4Ogg6MHFI9TGv/sq2DKsMBwSnfyZ/E9pjhXIqvxQtc/woBuGyq4Vk
nmT/QPSt9MEMCUBNU2JZe3yOhLaleKeD53i1mWsFMjO0Iq/nmNTsg0QbKaphpiUr
Izmr2jIJBl2MvFgQWtrvMYM=
-----END PRIVATE KEY-----
""",
    public_jwk={
        "alg": "RS256",
        "kty": "RSA",
        "n": (
            "065cm5vw-A5Qg8bvn1aJeb9jRP19OUDNtJP_-b3l3e2I36TMkCS6I8Xiv_SgkX2q4xcac_9--jy6ya3"
            "KjHHaaDXMuTCTcCpyRUa9j8UyrfuWlwYUIesqfD6L8yjY6oxSwZqtDgZ3R8wc35661UMXWGyNpA_SPi-"
            "V6JXOU_TnLoAJPxurnGKBCBG0SSNd_-u1Ofh-vvllIxvvlYRLk2zAzDAGZk2ziJ6o4EKgmriTEdjS2H1"
            "Y6qfmZgMs7u8A4J3omvMDQ7YbEjF0qLuDkHBMtrRdpVVtu-i7Qe2XXXyaVoVxqGA-JgjHbk3JrESw_p4"
            "O8RIlavGEc7CV8-CJPQnGQw"
        ),
        "e": "AQAB",
        "kid": "test-chat-key-1",
        "use": "sig",
    },
)
TEST_JWKS = {"keys": [TEST_KEY_PAIR.public_jwk]}

# A second, unrelated key: same kid as TEST_KEY_PAIR, but the service never
# sees its public half. A token signed with this proves "wrong key" is
# rejected, distinctly from "unknown kid".
OTHER_KEY_PAIR = _KeyPair(
    kid=TEST_KEY_PAIR.kid,
    private_pem="""-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQCa/iCK6Jt77ZGC
L27CJRnSLVAh4X7ioADMJ3ZcfuQTGA3gJ9Geq7XhFnfoL4o4Cl/bJ60JsNqXoowd
EnhhN1mRlpJwZsgG+41QsXcP6HLTcZD8I9vmpJ1B7m3Rrpf1HNK4o+HXeTmnfxSs
e0VG4IQXn+n2zPmIBGtd3TIsZlAg2mdem5O+g+apm993e+r6FVOuTmEa95QTSw0R
eVygUoMj0xwYWfcyjAmWReJiGi0V5BK01BXmfBV9TzKmNdQvDO2zVPAspgWt3czF
OG1tpZYCcpsiNmzMoLjb2sRLCfZkPI4OWDz3BZAOsw7VM38bjU8hQHal3ZyUi9cY
8xBCmkpZAgMBAAECggEAAWHf121Qqa/KOu+CXN/o1YuK6epxb8L+jtORRizpitQN
l6CzSWd9pUbGhf8ai/pntXQqomn94RlVh5LZGQDd3yMJJlB8WzeWIJCcn7syfvlF
0kHdnbZ9Io/mUdbtSwXZSUVI59uQbJKBFDK7QPESrIVEGGvmk9R6QqmM34GAGHLm
pUKAI5ajwqzgD68ZmUUysiM0BUyUytAu23V00jLrZ6f3oBKVKXmIeyJaiw3SCl/u
2d3rZeREMdJ2Ri4TY6uNi9yn5e//A9T2Mx7Vb6KpM6xI+9NQm+IXeu0DaW+Mq/bE
ibTLxU3QyJHH9g8o8+KrVGh9pTQh++riNSL362gggQKBgQDYxPayN3XBPtad8/96
3+4cxXsKV6lu0/3Ya23cdEJ7sZdbVXnJ/ddW1If/g6B9ayp2Wgoay5ErcNNeii21
f2AITB0It5/U3kQoKkwCTlU+i2Cp8Q/z9rHsZT1SfbLoYGe8X1OlnolwiFL8CXY5
M2lUwAKGHHL4S58S+kg1SmhFeQKBgQC3CwRnutV+aIVtERo00AEf/MxDDX+Y66hz
N8Fb+H6S6Pt3KbXPA8kVcsIwNpG72EljgTZ79E2kJum4PEoBc+qOgFBRME6yh1fu
lodwZEDdV1J5yzBa91m512llV4pAYH2o9ntLT+gMFcks7PkNYyjrrG8wZZlsa5VV
hUwCASdT4QKBgDrDOjUZv7xBMqDjEjDXH4+BIVeuZ+n5YekXRlLq2VL605MY2skd
HREW0D8+CXW2ZW5r/i1BXfsuvL32K2n2O6xEJeLFFHj6P/O7c5t0bLtlwTCQfsid
6aGx2CvSk3tXFwgDt4NANPXinsxgLEJZY4Zr/sMoVypkJZ1ZZ9W6dAXRAoGBAKx6
Kyp7ONUmNCOzq9f78DNuCCNews8br9zxurepDcvs0ZdVrEVnMcGOI0E/Ck/Q3EZw
6SAf8lEtgani1XFNAsZITmZSeLVtJwRgvzq+nQh0UfkF54iv7tJZEq01scY7pezi
ZQdwQh2xIaG9omhk+ZgpIZSfB9TMAylUs2xoHeDBAoGBAIyUdM532eFcxarVYv2j
J0AyyQdSjPaaZHwO+aTsaeI9rsW5TnUnfun6hE4h86TjICBTFcA5/IX4xBQJh6m+
5KPmVBS7PcuA024gHjE0efR5xHCvEgEXL/HEb+TP8IHXDaIL0GGjdR9wfZUiRjZ9
gdl5Nr0YVC33MPf3UNIHPtpn
-----END PRIVATE KEY-----
""",
    public_jwk={},  # never published: that's the point of this key
)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unsigned_token(claims: dict[str, object], *, kid: str = TEST_KEY_PAIR.kid) -> str:
    """A token declaring `alg: none` — never produced by `jwt.encode`, built by hand.

    Exists to prove the classic algorithm-confusion attack is closed: a caller
    who can choose their own header must not be able to opt out of a
    signature check entirely.
    """
    header = _b64url(json.dumps({"alg": "none", "kid": kid, "typ": "JWT"}).encode())
    payload = _b64url(json.dumps(claims, default=str).encode())
    return f"{header}.{payload}."


def mint_chat_token(
    *,
    user_id: uuid.UUID | str | None = None,
    company_id: uuid.UUID | str | _Omitted | None = None,
    user_kind: str = "staff",
    scopes: list[str] | None = None,
    display_name: str = "Ana Souza",
    avatar_url: str | None = None,
    audience: str | None | _Omitted = OMITTED,
    issuer: str | None | _Omitted = OMITTED,
    kid: str | None = TEST_KEY_PAIR.kid,
    expires_in: timedelta | None = timedelta(minutes=15),
    key_pair: _KeyPair = TEST_KEY_PAIR,
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
    resolved_audience = settings.chat_token_audience if isinstance(audience, _Omitted) else audience
    if resolved_audience is not None:
        claims["aud"] = resolved_audience
    resolved_issuer = settings.chat_token_issuer if isinstance(issuer, _Omitted) else issuer
    if resolved_issuer is not None:
        claims["iss"] = resolved_issuer
    if expires_in is not None:
        claims["exp"] = datetime.now(timezone.utc) + expires_in

    headers = {"kid": kid} if kid is not None else {}
    return jwt.encode(claims, key_pair.private_pem, algorithm="RS256", headers=headers)


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
