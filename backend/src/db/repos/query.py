"""Repository module for the ``query`` table.

A ``query`` row captures the post-PII-masking text plus the
PII-detection outcome of one inbound user turn (FR-007, FR-008,
FR-009, FR-009a). The plaintext is never written here; only the
masked text or redaction tokens.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Text, func, select, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, RepoBase

PII_OUTCOMES: frozenset[str] = frozenset({"clean", "masked", "refused"})


class Query(Base):
    """One user-submitted turn (per :mod:`data-model.md`)."""

    __tablename__ = "query"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        init=False,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    masked_text: Mapped[str] = mapped_column(Text, nullable=False)
    pii_outcome: Mapped[str] = mapped_column(Text, nullable=False)
    pii_scanner_version: Mapped[str] = mapped_column(Text, nullable=False)
    pii_detected: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("'{}'::text[]"),
        default_factory=list,
    )
    language_detected: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        init=False,
    )

    __table_args__ = (
        CheckConstraint(
            "pii_outcome IN ('clean','masked','refused')",
            name="ck_query_pii_outcome",
        ),
    )


class QueryRepo(RepoBase):
    """Typed CRUD + PII-outcome write helper for ``query``."""

    async def create_with_pii_outcome(
        self,
        *,
        session_id: uuid.UUID,
        masked_text: str,
        pii_outcome: str,
        pii_scanner_version: str,
        pii_detected: list[str] | None = None,
        language_detected: str | None = None,
    ) -> Query:
        """Create a ``query`` row with the PII-guard outcome attached.

        The caller MUST already have applied the redaction step — this
        repo never stores plaintext PII (FR-009).
        """
        if pii_outcome not in PII_OUTCOMES:
            msg = f"invalid pii_outcome: {pii_outcome!r}"
            raise ValueError(msg)
        row = Query(
            session_id=session_id,
            masked_text=masked_text,
            pii_outcome=pii_outcome,
            pii_scanner_version=pii_scanner_version,
            pii_detected=list(pii_detected) if pii_detected is not None else [],
            language_detected=language_detected,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def get(self, query_id: uuid.UUID) -> Query | None:
        """Look up a query row by primary key."""
        stmt = select(Query).where(Query.id == query_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
