"""Repository module for the ``answer`` table.

A successful (non-refusal) generation lands here. The scoring columns
(``confidence_score``, ``correctness_score``, ``confidence_band``) are
NULLABLE in the v1 schema because the MVP user story (US1) writes
``answer`` rows before US7 lands the scoring node; US7 ships a migration
that backfills and tightens them to NOT NULL. See ``data-model.md``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    Text,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, RepoBase

CONFIDENCE_BANDS: frozenset[str] = frozenset({"high", "medium", "low"})


class Answer(Base):
    """A rendered answer (per :mod:`data-model.md`)."""

    __tablename__ = "answer"

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
    retrieval_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("retrieval.id"),
        nullable=False,
    )
    text_: Mapped[str] = mapped_column("text", Text, nullable=False)
    model_identity: Mapped[str] = mapped_column(Text, nullable=False)
    model_version: Mapped[str] = mapped_column(Text, nullable=False)
    generation_params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    per_answer_disclaimer_version: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True, default=None)
    correctness_score: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True, default=None)
    confidence_band: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        init=False,
    )

    __table_args__ = (
        CheckConstraint(
            "confidence_band IS NULL OR confidence_band IN ('high','medium','low')",
            name="ck_answer_confidence_band",
        ),
    )


class AnswerRepo(RepoBase):
    """Typed CRUD + scoring writes for ``answer``."""

    async def create(
        self,
        *,
        query_id: uuid.UUID,
        retrieval_id: uuid.UUID,
        text_value: str,
        model_identity: str,
        model_version: str,
        generation_params: dict[str, Any],
        per_answer_disclaimer_version: str,
        confidence_score: Decimal | None = None,
        correctness_score: Decimal | None = None,
        confidence_band: str | None = None,
    ) -> Answer:
        """Insert an ``answer`` row.

        Scoring columns are kept optional so the US1 happy-path flow can
        write an answer before US7's scoring node lands. The downstream
        US7 migration tightens them.
        """
        if confidence_band is not None and confidence_band not in CONFIDENCE_BANDS:
            msg = f"invalid confidence_band: {confidence_band!r}"
            raise ValueError(msg)
        row = Answer(
            query_id=query_id,
            retrieval_id=retrieval_id,
            text_=text_value,
            model_identity=model_identity,
            model_version=model_version,
            generation_params=generation_params,
            per_answer_disclaimer_version=per_answer_disclaimer_version,
            confidence_score=confidence_score,
            correctness_score=correctness_score,
            confidence_band=confidence_band,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def get(self, answer_id: uuid.UUID) -> Answer | None:
        """Look up an answer by primary key."""
        stmt = select(Answer).where(Answer.id == answer_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_query(self, query_id: uuid.UUID) -> Answer | None:
        """Return the most recent answer row for a query."""
        stmt = (
            select(Answer)
            .where(Answer.query_id == query_id)
            .order_by(Answer.generated_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
