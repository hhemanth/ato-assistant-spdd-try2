"""Repository module for the ``eval_run`` table.

Per-execution metadata of the harness CLI (FR-024). Aggregate metrics
land here as the run finishes; per-question rows live in
:mod:`db.repos.eval_result`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Numeric,
    Text,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, RepoBase

EXIT_STATUSES: frozenset[str] = frozenset({"pass", "fail", "partial"})


class EvalRun(Base):
    """One harness run (per :mod:`data-model.md`)."""

    __tablename__ = "eval_run"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        init=False,
    )
    commit_sha: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    harness_version: Mapped[str] = mapped_column(Text, nullable=False)
    corpus_index_version: Mapped[str] = mapped_column(Text, nullable=False)
    exit_status: Mapped[str] = mapped_column(Text, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    aggregate_citation_correctness: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, default=None
    )
    aggregate_refusal_correctness: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, default=None
    )
    aggregate_groundedness: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, default=None
    )

    __table_args__ = (
        CheckConstraint(
            "exit_status IN ('pass','fail','partial')",
            name="ck_eval_run_exit_status",
        ),
    )


class EvalRunRepo(RepoBase):
    """Typed CRUD for ``eval_run``."""

    async def start(
        self,
        *,
        commit_sha: str,
        started_at: datetime,
        harness_version: str,
        corpus_index_version: str,
    ) -> EvalRun:
        """Insert an in-flight eval run (``exit_status='partial'``)."""
        row = EvalRun(
            commit_sha=commit_sha,
            started_at=started_at,
            harness_version=harness_version,
            corpus_index_version=corpus_index_version,
            exit_status="partial",
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def finalize(
        self,
        eval_run_id: uuid.UUID,
        *,
        finished_at: datetime,
        exit_status: str,
        aggregate_citation_correctness: Decimal | None = None,
        aggregate_refusal_correctness: Decimal | None = None,
        aggregate_groundedness: Decimal | None = None,
    ) -> None:
        """Record the final aggregates + exit status (FR-025)."""
        if exit_status not in EXIT_STATUSES:
            msg = f"invalid exit_status: {exit_status!r}"
            raise ValueError(msg)
        stmt = (
            update(EvalRun)
            .where(EvalRun.id == eval_run_id)
            .values(
                finished_at=finished_at,
                exit_status=exit_status,
                aggregate_citation_correctness=aggregate_citation_correctness,
                aggregate_refusal_correctness=aggregate_refusal_correctness,
                aggregate_groundedness=aggregate_groundedness,
            )
        )
        await self.session.execute(stmt)

    async def get(self, eval_run_id: uuid.UUID) -> EvalRun | None:
        """Look up an eval run by primary key."""
        stmt = select(EvalRun).where(EvalRun.id == eval_run_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
