"""Repository module for the ``eval_question`` table.

Mirror of the golden-set YAML (``backend/data/golden_set.yaml``) loaded
into Postgres so eval reports can JOIN across runs (per FR-023 and
:mod:`data-model.md`).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Text,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, RepoBase

EXPECTED_OUTCOMES: frozenset[str] = frozenset({"answer", "refusal"})
TOPICS: frozenset[str] = frozenset(
    {
        "gst",
        "income-tax",
        "tax-free-threshold",
        "deductions",
        "bas",
        "payg",
        "refusal",
        "other",
    }
)
DIFFICULTIES: frozenset[str] = frozenset({"easy", "medium", "hard"})


class EvalQuestion(Base):
    """One entry from the 30-question golden set (per :mod:`data-model.md`)."""

    __tablename__ = "eval_question"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        init=False,
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    expected_outcome: Mapped[str] = mapped_column(Text, nullable=False)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str] = mapped_column(Text, nullable=False)
    expected_refusal_reason: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    expected_citation_urls: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("'{}'::text[]"),
        default_factory=list,
    )
    reviewed_by: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        init=False,
    )

    __table_args__ = (
        CheckConstraint(
            "expected_outcome IN ('answer','refusal')",
            name="ck_eval_question_expected_outcome",
        ),
        CheckConstraint(
            "topic IN ("
            "'gst','income-tax','tax-free-threshold','deductions',"
            "'bas','payg','refusal','other')",
            name="ck_eval_question_topic",
        ),
        CheckConstraint(
            "difficulty IN ('easy','medium','hard')",
            name="ck_eval_question_difficulty",
        ),
    )


@dataclass(frozen=True, slots=True)
class EvalQuestionInput:
    """Payload for :meth:`EvalQuestionRepo.bulk_upsert`."""

    question_text: str
    expected_outcome: str
    topic: str
    difficulty: str
    author: str
    expected_refusal_reason: str | None = None
    expected_citation_urls: tuple[str, ...] = ()
    reviewed_by: str | None = None


class EvalQuestionRepo(RepoBase):
    """Typed bulk-load + lookups for ``eval_question``."""

    async def bulk_upsert(
        self, questions: Sequence[EvalQuestionInput]
    ) -> list[EvalQuestion]:
        """Insert a batch of golden-set rows."""
        rows: list[EvalQuestion] = []
        for q in questions:
            if q.expected_outcome not in EXPECTED_OUTCOMES:
                msg = f"invalid expected_outcome: {q.expected_outcome!r}"
                raise ValueError(msg)
            if q.topic not in TOPICS:
                msg = f"invalid topic: {q.topic!r}"
                raise ValueError(msg)
            if q.difficulty not in DIFFICULTIES:
                msg = f"invalid difficulty: {q.difficulty!r}"
                raise ValueError(msg)
            row = EvalQuestion(
                question_text=q.question_text,
                expected_outcome=q.expected_outcome,
                topic=q.topic,
                difficulty=q.difficulty,
                author=q.author,
                expected_refusal_reason=q.expected_refusal_reason,
                expected_citation_urls=list(q.expected_citation_urls),
                reviewed_by=q.reviewed_by,
            )
            self.session.add(row)
            rows.append(row)
        await self.session.flush()
        return rows

    async def get(self, eval_question_id: uuid.UUID) -> EvalQuestion | None:
        """Look up an eval question by primary key."""
        stmt = select(EvalQuestion).where(EvalQuestion.id == eval_question_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self) -> list[EvalQuestion]:
        """Return every eval question, in creation order."""
        stmt = select(EvalQuestion).order_by(EvalQuestion.created_at.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
