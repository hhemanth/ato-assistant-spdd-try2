"""Repository module for the ``retrieval`` table.

A ``retrieval`` row captures the ranked chunks and similarities returned
for one ``query`` (per :mod:`data-model.md`).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, RepoBase


class Retrieval(Base):
    """Per-query retrieval result row."""

    __tablename__ = "retrieval"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        init=False,
    )
    query_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("query.id", ondelete="CASCADE"),
        nullable=False,
    )
    top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=False)
    similarities: Mapped[list[Decimal]] = mapped_column(ARRAY(Numeric), nullable=False)
    embedding_model_version: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        init=False,
    )


class RetrievalRepo(RepoBase):
    """Typed CRUD for ``retrieval``."""

    async def create(
        self,
        *,
        query_id: uuid.UUID,
        top_k: int,
        chunk_ids: list[uuid.UUID],
        similarities: list[Decimal],
        embedding_model_version: str,
    ) -> Retrieval:
        """Insert a retrieval result row."""
        if len(chunk_ids) != len(similarities):
            msg = "chunk_ids and similarities MUST be the same length"
            raise ValueError(msg)
        row = Retrieval(
            query_id=query_id,
            top_k=top_k,
            chunk_ids=list(chunk_ids),
            similarities=list(similarities),
            embedding_model_version=embedding_model_version,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def get(self, retrieval_id: uuid.UUID) -> Retrieval | None:
        """Look up a retrieval row by primary key."""
        stmt = select(Retrieval).where(Retrieval.id == retrieval_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_query(self, query_id: uuid.UUID) -> Retrieval | None:
        """Return the most recent retrieval row for a query (one-per-turn)."""
        stmt = (
            select(Retrieval)
            .where(Retrieval.query_id == query_id)
            .order_by(Retrieval.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
