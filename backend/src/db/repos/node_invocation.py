"""Repository module for the ``node_invocation`` table.

Per-node model-invocation record so Principle V's transparency posture
extends to every LangGraph model call — not just the answer-generating
one (per :mod:`data-model.md`).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, RepoBase

NODE_NAMES: frozenset[str] = frozenset(
    {
        "pii_node",
        "pii_intent_classifier",
        "scope_safety_node",
        "boundary_classifier",
        "retrieval_node",
        "generation_node",
        "citation_check_node",
        "scoring_node",
        "finalize_node",
    }
)


class NodeInvocation(Base):
    """One LangGraph node invocation record (per :mod:`data-model.md`)."""

    __tablename__ = "node_invocation"

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
    node_name: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    model_identity: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    model_version: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    processing_region: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    input_token_count: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    output_token_count: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        init=False,
    )

    __table_args__ = (
        CheckConstraint(
            "node_name IN ("
            "'pii_node','pii_intent_classifier','scope_safety_node',"
            "'boundary_classifier','retrieval_node','generation_node',"
            "'citation_check_node','scoring_node','finalize_node')",
            name="ck_node_invocation_node_name",
        ),
        Index("ix_node_invocation_query_id", "query_id"),
    )


class NodeInvocationRepo(RepoBase):
    """Typed CRUD for ``node_invocation``."""

    async def record(
        self,
        *,
        query_id: uuid.UUID,
        node_name: str,
        started_at: datetime,
        finished_at: datetime,
        model_identity: str | None = None,
        model_version: str | None = None,
        processing_region: str | None = None,
        input_token_count: int | None = None,
        output_token_count: int | None = None,
    ) -> NodeInvocation:
        """Insert a node-invocation row."""
        if node_name not in NODE_NAMES:
            msg = f"invalid node_name: {node_name!r}"
            raise ValueError(msg)
        row = NodeInvocation(
            query_id=query_id,
            node_name=node_name,
            started_at=started_at,
            finished_at=finished_at,
            model_identity=model_identity,
            model_version=model_version,
            processing_region=processing_region,
            input_token_count=input_token_count,
            output_token_count=output_token_count,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def list_for_query(self, query_id: uuid.UUID) -> list[NodeInvocation]:
        """Return every node-invocation row for a given query, oldest first."""
        stmt = (
            select(NodeInvocation)
            .where(NodeInvocation.query_id == query_id)
            .order_by(NodeInvocation.started_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
