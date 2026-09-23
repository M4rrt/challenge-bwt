"""Who the monolith is acting for when it sends a command.

A composition command arrives with a service credential, which says *that* the
monolith sent it, and with headers saying *who* it sent it for. The second half
is what stops the service credential becoming an omnipotent one: it does not
widen what can be done, it only allows doing it on behalf of someone identified
(ADR-0010). There is no Chat without an author, so a command that names nobody
is refused rather than defaulted.

The Company travels with the identifier because a user id alone does not name a
user here — the same id can exist in two Companies, which `services/realtime.py`
already has to carry in every address for exactly that reason. It is also the
Company every row the command writes is filed under.

A created Chat keeps this identifier in `chats.created_by_user_id`, so "there is
no Chat without an author" is answerable afterwards and not only enforced at the
door. Adding and removing a Participant do not record it yet — the header is
still only a condition there, and attributing a join or a departure is another
column on `participants`.
"""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class ActingUser:
    id: uuid.UUID
    company_id: uuid.UUID
