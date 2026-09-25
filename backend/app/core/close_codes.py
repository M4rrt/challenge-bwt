"""The close codes, which are part of the WebSocket contract and not an implementation detail.

Three closures a client cannot treat alike (ADR-0011). Treating them all as
failure turns every routine expiry into a growing backoff; treating them all as
expiry makes a client hammer a Chat it was removed from. So each one is a number
the client can switch on:

- `UNAUTHENTICATED` — the credential was never good here. Do not retry with it.
- `TOKEN_EXPIRED` — it was good and ran out. Get a new one and reconnect.
- `ACCESS_REVOKED` — the credential is fine and this Chat is not yours. Leave it.

A network failure is deliberately none of these: it stays a plain socket error
and stays on exponential backoff, which is what makes the three codes mean
something.

`UNAUTHENTICATED` is 1008, the protocol's own policy-violation code, because
that is what the handshake has always answered and clients are written against
it. The other two are in the 4000–4999 range the protocol reserves for the
application, and their last three digits echo the HTTP statuses a reader will
already associate with "who are you" and "not for you".
"""

from enum import IntEnum


class CloseCode(IntEnum):
    UNAUTHENTICATED = 1008
    TOKEN_EXPIRED = 4401
    ACCESS_REVOKED = 4403
