"""The Company boundary: the one place a company-scoped read is built.

ADR-0007 moved Company isolation out of the database and into code. In the
source module it was a queryset invariant whose docstring said isolation lived
there and nowhere else, precisely so no call site had to remember it. Leaving
Django removed that floor, and the ADR names the loss as the central risk of the
architecture.

This module is the replacement floor. Every readable row carries the Company
that owns it (`CompanyScoped`), and every read of one starts from
`CompanyScope.select`, which takes the Company from the caller's token. No
service or router builds its own query over a scoped entity;
`tests/test_company_isolation.py` fails if one starts to.

A row belonging to another Company is not forbidden, it is absent: the filter
lands in the WHERE clause, so a cross-Company request and a request for
something that never existed produce the same empty result, and no response
distinguishes them.
"""

import uuid
from dataclasses import dataclass
from typing import TypeVar

from sqlalchemy import Select, Uuid, select
from sqlalchemy.orm import Mapped, mapped_column

from app.core.chat_token import Caller


class CompanyScoped:
    """A row owned by exactly one Company, and never read outside it."""

    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)


ScopedEntity = TypeVar("ScopedEntity", bound=CompanyScoped)


@dataclass(frozen=True)
class CompanyScope:
    """The caller's Company, and the only constructor of a readable query."""

    company_id: uuid.UUID

    @classmethod
    def of(cls, caller: Caller) -> "CompanyScope":
        return cls(company_id=caller.company_id)

    def select(self, entity: type[ScopedEntity]) -> Select[tuple[ScopedEntity]]:
        return select(entity).where(entity.company_id == self.company_id)
