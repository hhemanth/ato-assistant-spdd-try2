"""Shared declarative base and repository helpers for the ATO Assistant.

All ORM entities in ``backend/src/db/repos/`` inherit from :class:`Base`,
which combines SQLAlchemy 2.x typed declarative mappings with dataclass
semantics (``MappedAsDataclass``). The :class:`RepoBase` helper holds the
shared ``AsyncSession`` so concrete repositories can focus on
entity-specific lookups required by the spec FRs.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass


class Base(MappedAsDataclass, DeclarativeBase):
    """Declarative base for typed dataclass-style ORM models.

    Sub-classes use ``Mapped[<type>]`` annotations and let SQLAlchemy
    generate a typed ``__init__``. Columns whose values are produced by
    the database (UUID PKs, ``created_at``) MUST pass ``init=False`` to
    ``mapped_column(...)`` so the generated ``__init__`` does not require
    them at construction time.
    """


class RepoBase:
    """Common base for entity repositories.

    Concrete repositories accept an ``AsyncSession`` and expose
    entity-specific typed methods (create / lookup) referenced by the
    spec's functional requirements.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @property
    def session(self) -> AsyncSession:
        """Return the underlying async session."""
        return self._session
