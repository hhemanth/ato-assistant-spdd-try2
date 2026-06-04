"""pgvector retrieval client (T039).

A thin async facade that drives :meth:`db.repos.chunk.ChunkRepo.find_top_k_by_embedding`
and converts the repo's ``(Chunk, distance)`` rows into the
:class:`agents.state.RetrievedChunk` value object the rest of the
LangGraph speaks.

Hard filters
============

The constructor takes a ``corpus_scope`` URL prefix. It is forwarded
verbatim to the repo (which appends ``%`` for the SQL ``LIKE``); the
client MUST NOT silently mutate or drop the prefix because that would
let an upstream caller bypass FR-012's domain restriction. The
repo additionally enforces ``is_superseded = false`` on both the chunk
and its source document.

Distance → similarity
=====================

``find_top_k_by_embedding`` orders by *cosine distance* (lower = closer).
``RetrievedChunk.similarity`` is the user-facing similarity (higher =
closer). For pgvector's cosine distance the conversion is::

    similarity = 1.0 - distance

This is the formal cosine-similarity relationship — the value lies in
``[-1, 1]`` in general and in ``[0, 1]`` for L2-normalised vectors
(which Voyage embeddings effectively are).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from db.repos.chunk import ChunkRepo
from db.repos.source_document import SourceDocument

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractAsyncContextManager

    from sqlalchemy.ext.asyncio import AsyncSession

    from agents.state import RetrievedChunk


#: FR-012 hard scope: the corpus is restricted to ``www.ato.gov.au``.
#: The trailing ``/`` ensures the ``LIKE`` filter does not also match
#: sibling hostnames such as ``www.ato.gov.au.evil.example``.
DEFAULT_CORPUS_SCOPE: str = "https://www.ato.gov.au/"


class PgVectorClient:
    """Async pgvector retrieval client used by ``retrieval_node``.

    Parameters
    ----------
    session_factory:
        Zero-arg callable returning an ``AsyncSession`` context manager.
        In production this is :func:`db.repos.get_sessionmaker`; tests
        substitute an in-memory factory bound to a transactional
        rollback.
    corpus_scope:
        URL prefix the retrieval is restricted to. Defaults to
        :data:`DEFAULT_CORPUS_SCOPE` (= ``https://www.ato.gov.au/``).
        Forwarded to the repo unmodified — see module docstring.
    """

    def __init__(
        self,
        *,
        session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
        corpus_scope: str = DEFAULT_CORPUS_SCOPE,
    ) -> None:
        if not corpus_scope:
            raise ValueError("corpus_scope must be a non-empty URL prefix")
        self._session_factory = session_factory
        self._corpus_scope = corpus_scope

    @property
    def corpus_scope(self) -> str:
        """The URL prefix forwarded to the repo's hard filter."""
        return self._corpus_scope

    async def top_k(self, query_embedding: list[float], k: int = 8) -> list[RetrievedChunk]:
        """Return the top-``k`` chunks for ``query_embedding`` (FR-012).

        Hard-restricted by ``corpus_scope`` (FR-012) and the
        ``is_superseded = false`` filter enforced inside
        :meth:`db.repos.chunk.ChunkRepo.find_top_k_by_embedding`.

        Implementation note: the repo returns ``(Chunk, distance)`` only.
        :class:`agents.state.RetrievedChunk` also requires
        ``source_url`` and ``source_last_modified`` — we run a single
        batch ``SELECT`` against :class:`SourceDocument` keyed on the
        returned chunks' ``source_document_id``s rather than an N+1
        loop. The repo surface is not expanded.
        """

        # Local import keeps ``agents.state`` (a TypedDict module the
        # whole graph imports) out of this module's import-time graph
        # so the retrieval client can be unit-tested without the
        # graph's other transitive imports.
        from agents.state import RetrievedChunk  # noqa: PLC0415

        if k <= 0:
            return []

        async with self._session_factory() as session:
            chunk_repo = ChunkRepo(session)
            rows = await chunk_repo.find_top_k_by_embedding(
                query_vec=query_embedding,
                top_k=k,
                scope_url_prefix=self._corpus_scope,
            )

            if not rows:
                return []

            source_doc_ids = {chunk.source_document_id for chunk, _ in rows}
            stmt = select(
                SourceDocument.id,
                SourceDocument.source_url,
                SourceDocument.source_last_modified,
            ).where(SourceDocument.id.in_(source_doc_ids))
            result = await session.execute(stmt)
            sources = {row[0]: (row[1], row[2]) for row in result.all()}

        retrieved: list[RetrievedChunk] = []
        for chunk, distance in rows:
            source_url, source_last_modified = sources[chunk.source_document_id]
            retrieved.append(
                RetrievedChunk(
                    chunk_id=chunk.id,
                    source_url=source_url,
                    snippet=chunk.text_,
                    similarity=1.0 - float(distance),
                    source_last_modified=source_last_modified,
                )
            )
        return retrieved
