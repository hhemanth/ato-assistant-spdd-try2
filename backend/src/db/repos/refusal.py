"""Repository module for the ``refusal`` table.

Each row records one refusal outcome with its reason code and the
LangGraph node that produced it (per :mod:`data-model.md`, FR-005).
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

REASON_CODES: frozenset[str] = frozenset(
    {
        "no-source",
        "low-confidence",
        "citation-misalignment",
        "stale-source",
        "pii-integral",
        "pii-scanner-fail",
        "out-of-scope",
        "inappropriate",
        "personal-advice",
        "non-english",
    }
)

REFUSAL_NODES: frozenset[str] = frozenset(
    {
        "pii_node",
        "scope_safety_node",
        "retrieval_node",
        "generation_node",
        "citation_check_node",
        "scoring_node",
    }
)


class Refusal(Base):
    """A non-answer response (per :mod:`data-model.md`)."""

    __tablename__ = "refusal"

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
    reason_code: Mapped[str] = mapped_column(Text, nullable=False)
    user_message: Mapped[str] = mapped_column(Text, nullable=False)
    produced_by_node: Mapped[str] = mapped_column(Text, nullable=False)
    refused_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        init=False,
    )

    __table_args__ = (
        CheckConstraint(
            "reason_code IN ("
            "'no-source','low-confidence','citation-misalignment','stale-source',"
            "'pii-integral','pii-scanner-fail','out-of-scope','inappropriate',"
            "'personal-advice','non-english')",
            name="ck_refusal_reason_code",
        ),
        CheckConstraint(
            "produced_by_node IN ("
            "'pii_node','scope_safety_node','retrieval_node',"
            "'generation_node','citation_check_node','scoring_node')",
            name="ck_refusal_produced_by_node",
        ),
    )


class RefusalRepo(RepoBase):
    """Typed CRUD for ``refusal``."""

    async def create(
        self,
        *,
        query_id: uuid.UUID,
        reason_code: str,
        user_message: str,
        produced_by_node: str,
    ) -> Refusal:
        """Insert a refusal row."""
        if reason_code not in REASON_CODES:
            msg = f"invalid reason_code: {reason_code!r}"
            raise ValueError(msg)
        if produced_by_node not in REFUSAL_NODES:
            msg = f"invalid produced_by_node: {produced_by_node!r}"
            raise ValueError(msg)
        row = Refusal(
            query_id=query_id,
            reason_code=reason_code,
            user_message=user_message,
            produced_by_node=produced_by_node,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def get(self, refusal_id: uuid.UUID) -> Refusal | None:
        """Look up a refusal row by primary key."""
        stmt = select(Refusal).where(Refusal.id == refusal_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_query(self, query_id: uuid.UUID) -> Refusal | None:
        """Return the most recent refusal row for a query."""
        stmt = (
            select(Refusal)
            .where(Refusal.query_id == query_id)
            .order_by(Refusal.refused_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
