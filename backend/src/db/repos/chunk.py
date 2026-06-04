"""Repository module for the ``chunk`` table.

``chunk`` rows are the retrievable units the LangGraph retrieval node
queries. The repository enforces the FR-012 hard domain filter
(`https://www.ato.gov.au/` prefix) and supports the FR-022 supersede
flow.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, RepoBase
from .source_document import SourceDocument

#: Voyage ``voyage-3-large`` embedding dimension (verified in T010).
VOYAGE_LARGE_DIM: int = 1024


class Chunk(Base):
    """A retrievable text chunk derived from a :class:`SourceDocument`."""

    __tablename__ = "chunk"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        init=False,
    )
    source_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("source_document.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text_: Mapped[str] = mapped_column("text", Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(VOYAGE_LARGE_DIM), nullable=False)
    is_superseded: Mapped[bool] = mapped_column(
        nullable=False, server_default=text("false"), default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        init=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "source_document_id", "chunk_index", name="uq_chunk_source_doc_chunk_index"
        ),
        Index(
            "ix_chunk_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class ChunkRepo(RepoBase):
    """Typed retrieval + supersede helpers for ``chunk``."""

    async def insert(
        self,
        *,
        source_document_id: uuid.UUID,
        chunk_index: int,
        text_value: str,
        token_count: int,
        embedding: list[float],
    ) -> Chunk:
        """Insert a single chunk row."""
        row = Chunk(
            source_document_id=source_document_id,
            chunk_index=chunk_index,
            text_=text_value,
            token_count=token_count,
            embedding=embedding,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def get(self, chunk_id: uuid.UUID) -> Chunk | None:
        """Look up a chunk by primary key."""
        stmt = select(Chunk).where(Chunk.id == chunk_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_top_k_by_embedding(
        self,
        *,
        query_vec: list[float],
        top_k: int,
        scope_url_prefix: str = "https://www.ato.gov.au/",
    ) -> list[tuple[Chunk, float]]:
        """Return the top-k closest chunks to ``query_vec`` (FR-012).

        Enforces two hard filters:

        * the chunk's source document URL MUST begin with
          ``scope_url_prefix`` (default ``https://www.ato.gov.au/``);
        * the chunk MUST NOT be superseded.

        Returns chunks paired with their cosine distance (lower is
        closer) ordered ascending.
        """
        distance = Chunk.embedding.cosine_distance(query_vec)
        stmt = (
            select(Chunk, distance.label("distance"))
            .join(SourceDocument, SourceDocument.id == Chunk.source_document_id)
            .where(
                Chunk.is_superseded.is_(False),
                SourceDocument.is_superseded.is_(False),
                SourceDocument.source_url.like(f"{scope_url_prefix}%"),
            )
            .order_by(distance.asc())
            .limit(top_k)
        )
        result = await self.session.execute(stmt)
        return [(row[0], float(row[1])) for row in result.all()]

    async def mark_superseded_for_source(self, source_document_id: uuid.UUID) -> None:
        """Bulk-mark every chunk of a source document as superseded (FR-022)."""
        stmt = (
            update(Chunk)
            .where(Chunk.source_document_id == source_document_id)
            .values(is_superseded=True)
        )
        await self.session.execute(stmt)

    async def get_provenance(self, chunk_id: uuid.UUID) -> ChunkProvenance | None:
        """Return full chunk provenance for an auditor (FR-018)."""
        stmt = (
            select(
                Chunk.id,
                SourceDocument.source_url,
                SourceDocument.fetched_at,
                SourceDocument.content_hash,
                SourceDocument.source_last_modified,
            )
            .join(SourceDocument, SourceDocument.id == Chunk.source_document_id)
            .where(Chunk.id == chunk_id)
        )
        result = await self.session.execute(stmt)
        row = result.one_or_none()
        if row is None:
            return None
        return ChunkProvenance(
            chunk_id=row[0],
            source_url=row[1],
            fetched_at=row[2],
            content_hash=row[3],
            source_last_modified=row[4],
        )


class ChunkProvenance:
    """Plain typed value object returned by :meth:`ChunkRepo.get_provenance`.

    Kept distinct from the ORM ``Chunk`` model so the auditor surface is
    insulated from schema details (no risk of leaking a lazy-loaded
    embedding into a JSON response).
    """

    __slots__ = (
        "chunk_id",
        "content_hash",
        "fetched_at",
        "source_last_modified",
        "source_url",
    )

    def __init__(
        self,
        *,
        chunk_id: uuid.UUID,
        source_url: str,
        fetched_at: datetime,
        content_hash: bytes,
        source_last_modified: datetime | None,
    ) -> None:
        self.chunk_id = chunk_id
        self.source_url = source_url
        self.fetched_at = fetched_at
        self.content_hash = content_hash
        self.source_last_modified = source_last_modified
