"""What the monolith sends when fifteen minutes is too long to wait."""

import uuid
from typing import Self

from pydantic import BaseModel, model_validator


class RevocationEvent(BaseModel):
    """Either a person or a single credential — and exactly one of the two.

    The person is the ordinary shape: a dismissal or a ban takes away everything
    they hold. One token is the narrow instrument, for a credential believed
    leaked while its owner keeps their access.

    Naming neither is refused rather than accepted as a no-op. The monolith
    delivers at-least-once, so a command that revoked nothing and answered
    success would be retried, succeed identically, and be believed.
    """

    company_id: uuid.UUID
    user_id: uuid.UUID | None = None
    token: str | None = None

    @model_validator(mode="after")
    def names_exactly_one(self) -> Self:
        if (self.user_id is None) == (self.token is None):
            raise ValueError(
                "a revocation names either a user or a token, not both and not neither"
            )
        return self
