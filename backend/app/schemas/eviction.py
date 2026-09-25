"""An instruction to close connections, travelling the same Redis path as a delivery.

It is not a delivery. A delivery names an audience — a channel — and the
subscriber forwards it without knowing who is listening. This names *sockets*:
this person's, either everywhere or only in one Chat. That is a different
question, and one no channel name can answer, because losing a Chat has to leave
every other connection of theirs alone.

It goes on a channel of its own (`control:{company}`) so that the delivery path
decides by channel prefix and never by looking inside a payload. Sniffing a
`type` field out of every frame would put a rule back on the hot path, which is
the mistake ADR-0008 records.

The Company is in the channel and restated here: the drain hands `publish` only
the address it stored, so what the instruction does not carry, the instance
receiving it does not know.
"""

import uuid

from pydantic import BaseModel


class Eviction(BaseModel):
    company_id: uuid.UUID
    user_id: uuid.UUID
    chat_id: uuid.UUID | None = None
    """The one Chat to close them out of, or every connection they hold."""
