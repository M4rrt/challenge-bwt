from collections.abc import AsyncGenerator
from enum import StrEnum

from sqlalchemy import Enum
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(settings.database_url)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def stored_by_value(enum: type[StrEnum], name: str) -> Enum:
    """A VARCHAR column holding the enum's values, checked in the database.

    Two defaults have to be overridden together. SQLAlchemy stores a Python
    enum by member *name*, so `ChatType.STAFF` would land as `STAFF` while
    every migration, payload and log says `staff` — invisible until something
    reads the column without going through the mapper. And `create_constraint`
    is off by default, which leaves the set of legal values as a claim the
    schema does not make.
    """
    return Enum(
        enum,
        native_enum=False,
        create_constraint=True,
        values_callable=lambda members: [member.value for member in members],
        name=name,
    )


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session
