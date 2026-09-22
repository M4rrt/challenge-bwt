import uuid

from pydantic import BaseModel


class CallerRead(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    user_kind: str
    scopes: list[str]
    display_name: str | None
    avatar_url: str | None
