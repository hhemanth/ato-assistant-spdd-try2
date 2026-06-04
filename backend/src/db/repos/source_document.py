"""Repository module for the ``source_document`` table.

A ``source_document`` row is one snapshot of a fetched
``www.ato.gov.au`` HTML page. The repository exposes the typed lookups
required by FR-018 (full provenance retrieval) and FR-022 (supersede on
content-hash change).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Index,
    Integer,
    LargeBinary,
    Text,
    func,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, RepoBase


class SourceDocument(Base):
    """One snapshot of a fetched ATO page (per :mod:`data-model.md`)."""

    __tablename__ = "source_document"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        init=False,
    )
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    main_text: Mapped[str] = mapped_column(Text, nullable=False)
    http_status: Mapped[int] = mapped_column(Integer, nullable=False)
    source_last_modified: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    extraction_warnings: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb"), default_factory=list
    )
    is_superseded: Mapped[bool] = mapped_column(
        nullable=False, server_default=text("false"), default=False
    )
    superseded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        init=False,
    )

    __table_args__ = (
        Index(
            "ix_source_document_active_url",
            "source_url",
            unique=True,
            postgresql_where=text("is_superseded = false"),
        ),
        Index("ix_source_document_content_hash", "content_hash"),
    )


class SourceDocumentRepo(RepoBase):
    """Typed CRUD + supersede helpers for ``source_document``."""

    async def insert(
        self,
        *,
        source_url: str,
        fetched_at: datetime,
        content_hash: bytes,
        main_text: str,
        http_status: int,
        source_last_modified: datetime | None = None,
        extraction_warnings: list[Any] | None = None,
    ) -> SourceDocument:
        """Insert a new source document snapshot."""
        row = SourceDocument(
            source_url=source_url,
            fetched_at=fetched_at,
            content_hash=content_hash,
            main_text=main_text,
            http_status=http_status,
            source_last_modified=source_last_modified,
            extraction_warnings=extraction_warnings if extraction_warnings is not None else [],
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def find_active_by_url(self, source_url: str) -> SourceDocument | None:
        """Return the active (non-superseded) snapshot for ``source_url``."""
        stmt = select(SourceDocument).where(
            SourceDocument.source_url == source_url,
            SourceDocument.is_superseded.is_(False),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get(self, source_document_id: uuid.UUID) -> SourceDocument | None:
        """Look up a source document by primary key."""
        stmt = select(SourceDocument).where(SourceDocument.id == source_document_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_superseded(
        self, source_document_id: uuid.UUID, *, superseded_at: datetime
    ) -> None:
        """Flip ``is_superseded`` true and record ``superseded_at`` (FR-022)."""
        stmt = (
            update(SourceDocument)
            .where(SourceDocument.id == source_document_id)
            .values(is_superseded=True, superseded_at=superseded_at)
        )
        await self.session.execute(stmt)
