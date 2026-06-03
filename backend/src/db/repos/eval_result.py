"""Repository module for the ``eval_result`` table (FR-024)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Numeric,
    Text,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, RepoBase

ACTUAL_OUTCOMES: frozenset[str] = frozenset({"answer", "refusal"})
VERDICTS: frozenset[str] = frozenset(
    {"pass", "fail", "refused_correct", "refused_incorrect"}
)


class EvalResult(Base):
    """Per-question outcome of an eval run (per :mod:`data-model.md`)."""

    __tablename__ = "eval_result"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        init=False,
    )
    eval_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("eval_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    eval_question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("eval_question.id"),
        nullable=False,
    )
    actual_outcome: Mapped[str] = mapped_column(Text, nullable=False)
    actual_text: Mapped[str] = mapped_column(Text, nullable=False)
    verdict: Mapped[str] = mapped_column(Text, nullable=False)
    actual_citation_urls: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("'{}'::text[]"),
        default_factory=list,
    )
    citation_correctness: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, default=None
    )
    groundedness: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, default=None
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    __table_args__ = (
        CheckConstraint(
            "actual_outcome IN ('answer','refusal')",
            name="ck_eval_result_actual_outcome",
        ),
        CheckConstraint(
            "verdict IN ('pass','fail','refused_correct','refused_incorrect')",
            name="ck_eval_result_verdict",
        ),
    )


@dataclass(frozen=True, slots=True)
class EvalResultInput:
    """Payload for :meth:`EvalResultRepo.create_many`."""

    eval_question_id: uuid.UUID
    actual_outcome: str
    actual_text: str
    verdict: str
    actual_citation_urls: tuple[str, ...] = ()
    citation_correctness: Decimal | None = None
    groundedness: Decimal | None = None
    notes: str | None = None


class EvalResultRepo(RepoBase):
    """Typed batch CRUD + lookups for ``eval_result``."""

    async def create_many(
        self, *, eval_run_id: uuid.UUID, results: Sequence[EvalResultInput]
    ) -> list[EvalResult]:
        """Insert per-question results for a run."""
        rows: list[EvalResult] = []
        for r in results:
            if r.actual_outcome not in ACTUAL_OUTCOMES:
                msg = f"invalid actual_outcome: {r.actual_outcome!r}"
                raise ValueError(msg)
            if r.verdict not in VERDICTS:
                msg = f"invalid verdict: {r.verdict!r}"
                raise ValueError(msg)
            row = EvalResult(
                eval_run_id=eval_run_id,
                eval_question_id=r.eval_question_id,
                actual_outcome=r.actual_outcome,
                actual_text=r.actual_text,
                verdict=r.verdict,
                actual_citation_urls=list(r.actual_citation_urls),
                citation_correctness=r.citation_correctness,
                groundedness=r.groundedness,
                notes=r.notes,
            )
            self.session.add(row)
            rows.append(row)
        await self.session.flush()
        return rows

    async def list_for_run(self, eval_run_id: uuid.UUID) -> list[EvalResult]:
        """Return every result row for an eval run."""
        stmt = select(EvalResult).where(EvalResult.eval_run_id == eval_run_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
