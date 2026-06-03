"""Repository module for the ``citation`` table.

Each row is a typed pointer from an ``answer`` to a ``chunk`` and its
parent ATO URL (per :mod:`data-model.md`). The citation-alignment node
(FR-013) writes these rows after verifying every cited URL appears in
the retrieval result.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Text,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, RepoBase

LIVENESS_STATUSES: frozenset[str] = frozenset({"live", "unknown", "stale"})


class Citation(Base):
    """Per-answer citation row (per :mod:`data-model.md`)."""

    __tablename__ = "citation"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        init=False,
    )
    answer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("answer.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chunk.id"),
        nullable=False,
    )
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    snippet: Mapped[str] = mapped_column(Text, nullable=False)
    liveness_status: Mapped[str] = mapped_column(Text, nullable=False)
    anchor: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    source_last_modified_at_cite: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    liveness_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    __table_args__ = (
        CheckConstraint(
            "liveness_status IN ('live','unknown','stale')",
            name="ck_citation_liveness_status",
        ),
    )


@dataclass(frozen=True, slots=True)
class CitationInput:
    """Typed payload accepted by :meth:`CitationRepo.create_many`."""

    chunk_id: uuid.UUID
    source_url: str
    snippet: str
    liveness_status: str
    anchor: str | None = None
    source_last_modified_at_cite: datetime | None = None
    liveness_checked_at: datetime | None = None


class CitationRepo(RepoBase):
    """Typed batch insert + lookup for ``citation``."""

    async def create_many(
        self, *, answer_id: uuid.UUID, citations: Sequence[CitationInput]
    ) -> list[Citation]:
        """Insert one or more citation rows for an answer."""
        rows: list[Citation] = []
        for c in citations:
            if c.liveness_status not in LIVENESS_STATUSES:
                msg = f"invalid liveness_status: {c.liveness_status!r}"
                raise ValueError(msg)
            row = Citation(
                answer_id=answer_id,
                chunk_id=c.chunk_id,
                source_url=c.source_url,
                snippet=c.snippet,
                liveness_status=c.liveness_status,
                anchor=c.anchor,
                source_last_modified_at_cite=c.source_last_modified_at_cite,
                liveness_checked_at=c.liveness_checked_at,
            )
            self.session.add(row)
            rows.append(row)
        await self.session.flush()
        return rows

    async def list_for_answer(self, answer_id: uuid.UUID) -> list[Citation]:
        """Return every citation row attached to an answer."""
        stmt = select(Citation).where(Citation.answer_id == answer_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
