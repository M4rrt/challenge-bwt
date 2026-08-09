import re
import uuid

from pydantic import BaseModel, EmailStr, field_validator

PASSWORD_MIN_LENGTH = 8


class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str

    @field_validator("password")
    @classmethod
    def password_must_be_strong(cls, password: str) -> str:
        if (
            len(password) < PASSWORD_MIN_LENGTH
            or not re.search(r"[A-Z]", password)
            or not re.search(r"[a-z]", password)
            or not re.search(r"[\d\W]", password)
        ):
            raise ValueError(
                "password must be at least 8 characters and include "
                "an uppercase letter, a lowercase letter, and a digit or symbol"
            )
        return password


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserRead(BaseModel):
    id: uuid.UUID
    email: str
    username: str

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessToken(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class UserSummary(BaseModel):
    id: uuid.UUID
    username: str

    model_config = {"from_attributes": True}
