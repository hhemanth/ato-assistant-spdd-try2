"""Repository module for the ``audit_record`` table.

One row per user-facing turn (FR-017). Joins query, retrieval, and
either answer or refusal, plus the FR-018a processing-region columns.
The XOR constraint ensures exactly one of (answer_id, refusal_id) is
non-NULL.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Text,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, RepoBase


class AuditRecord(Base):
    """Per-turn audit row (per :mod:`data-model.md`)."""

    __tablename__ = "audit_record"

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
    processing_region_llm: Mapped[str] = mapped_column(Text, nullable=False)
    processing_region_embedding: Mapped[str] = mapped_column(Text, nullable=False)
    processing_region_observability: Mapped[str] = mapped_column(Text, nullable=False)
    answer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("answer.id"),
        nullable=True,
        default=None,
    )
    refusal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("refusal.id"),
        nullable=True,
        default=None,
    )
    retrieval_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("retrieval.id"),
        nullable=True,
        default=None,
    )
    langsmith_trace_id: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        init=False,
    )

    __table_args__ = (
        CheckConstraint(
            "(answer_id IS NULL) <> (refusal_id IS NULL)",
            name="ck_audit_record_answer_xor_refusal",
        ),
    )


class AuditRecordRepo(RepoBase):
    """Typed CRUD for ``audit_record`` (FR-017, FR-018a)."""

    async def write_turn(
        self,
        *,
        query_id: uuid.UUID,
        processing_region_llm: str,
        processing_region_embedding: str,
        processing_region_observability: str,
        answer_id: uuid.UUID | None = None,
        refusal_id: uuid.UUID | None = None,
        retrieval_id: uuid.UUID | None = None,
        langsmith_trace_id: str | None = None,
    ) -> AuditRecord:
        """Insert a per-turn audit record.

        Exactly one of ``answer_id`` or ``refusal_id`` MUST be set —
        the XOR is enforced both here (fail-fast) and at the DB layer.
        """
        if (answer_id is None) == (refusal_id is None):
            msg = "audit_record requires exactly one of answer_id, refusal_id"
            raise ValueError(msg)
        row = AuditRecord(
            query_id=query_id,
            processing_region_llm=processing_region_llm,
            processing_region_embedding=processing_region_embedding,
            processing_region_observability=processing_region_observability,
            answer_id=answer_id,
            refusal_id=refusal_id,
            retrieval_id=retrieval_id,
            langsmith_trace_id=langsmith_trace_id,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def get(self, audit_record_id: uuid.UUID) -> AuditRecord | None:
        """Look up an audit record by primary key."""
        stmt = select(AuditRecord).where(AuditRecord.id == audit_record_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_query(self, query_id: uuid.UUID) -> AuditRecord | None:
        """Return the audit record for a query (one row per turn)."""
        stmt = select(AuditRecord).where(AuditRecord.query_id == query_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
