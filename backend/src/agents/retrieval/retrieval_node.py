"""Retrieval LangGraph node (T040).

The retrieval node is the first "real model call" in the chat-turn graph.
It is responsible for:

1.  Embedding the (already PII-masked) user query via the Voyage embedder
    (T038).
2.  Running a top-``k`` cosine search against pgvector via the
    :class:`PgVectorClient` (T039), which enforces the FR-012 corpus
    scope (``https://www.ato.gov.au/``) and the
    ``is_superseded = false`` hard filter.
3.  Persisting a ``retrieval`` row capturing the ranked chunk ids, the
    similarity scores, the ``top_k``, and the embedding model version.
4.  Persisting a ``node_invocation`` row so Principle V's transparency
    posture (every model call is logged with identity, version, region,
    and timing) extends to the embedder call as well — the embedder is
    not a node, so the retrieval node owns its audit row.
5.  Writing the retrieved chunks plus the freshly-minted ``retrieval_id``
    onto :class:`ChatTurnState` for the downstream
    ``generation_node`` (T041).

Design notes
============

The class is constructed with three injected dependencies — an
``embedder``, a ``retrieval_client``, and a ``session_factory`` — so the
node is independently testable. Production wiring (T046) constructs a
single instance from real implementations; tests inject mocks (the
conftest's ``mocked_voyage`` fixture intercepts the embedder's HTTP
calls).

The ``processing_region`` recorded on the ``node_invocation`` row uses
:data:`audit.audit_writer.REGION_UNKNOWN` because Voyage's API does not
advertise a region in response headers. This matches the opaque-region
convention documented in :mod:`audit.audit_writer`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from audit.audit_writer import REGION_UNKNOWN, AuditWriter
from db.repos.audit_record import AuditRecordRepo
from db.repos.node_invocation import NodeInvocationRepo
from db.repos.retrieval import RetrievalRepo

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractAsyncContextManager

    from sqlalchemy.ext.asyncio import AsyncSession

    from agents.retrieval.pgvector_client import PgVectorClient
    from agents.state import ChatTurnState
    from ingestion.embedder.voyage_embedder import VoyageEmbedder


#: Default number of chunks retrieved per turn. ``8`` matches the
#: research.md retrieval budget and balances grounding coverage against
#: prompt size for the generation node.
DEFAULT_TOP_K: int = 8


class RetrievalNode:
    """LangGraph node implementing ``retrieval_node``.

    Satisfies :class:`agents.node_protocol.NodeProtocol` — exposes
    ``name``, ``model_identity``, ``model_version`` as class-level attrs
    plus an async ``__call__``.

    Parameters
    ----------
    embedder:
        Voyage AI embedder (T038). The node calls
        :meth:`VoyageEmbedder.embed_query` exactly once per turn.
    retrieval_client:
        pgvector retrieval client (T039) used for the top-``k`` search.
    session_factory:
        Async-session context-manager factory. Each call opens a fresh
        session for the ``retrieval`` + ``node_invocation`` writes. The
        retrieval client carries its own session factory for the read
        path; keeping the write factory injected lets T046 / tests
        rebind the write transaction independently.
    top_k:
        Number of chunks to retrieve. Defaults to :data:`DEFAULT_TOP_K`.
    """

    name: str = "retrieval_node"
    model_identity: str | None = "voyage-3-large"
    # The Voyage SDK does not expose a per-call model version distinct
    # from the model identifier; the identifier itself is the
    # version-pinned label.
    model_version: str | None = "voyage-3-large"

    def __init__(
        self,
        *,
        embedder: VoyageEmbedder,
        retrieval_client: PgVectorClient,
        session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
        top_k: int = DEFAULT_TOP_K,
    ) -> None:
        if top_k <= 0:
            raise ValueError(f"top_k must be positive, got {top_k}")
        self._embedder = embedder
        self._retrieval_client = retrieval_client
        self._session_factory = session_factory
        self._top_k = top_k

    async def __call__(self, state: ChatTurnState) -> ChatTurnState:
        """Embed the query, run top-``k``, persist audit rows, return state."""

        query_id = state["query_id"]
        # Prefer the PII-masked text when the upstream pii_node populated
        # it. Falls back to the original text for unit tests that exercise
        # the retrieval node in isolation.
        query_text = state.get("masked_text") or state["original_text"]

        started_at = datetime.now(tz=UTC)
        query_embedding = await self._embedder.embed_query(query_text)
        retrieved = await self._retrieval_client.top_k(query_embedding, k=self._top_k)
        finished_at = datetime.now(tz=UTC)

        # Write the ``retrieval`` row + the ``node_invocation`` audit row
        # in a single session so they share a transaction (the parent
        # graph wiring composes this with the rest of the turn's writes).
        async with self._session_factory() as session:
            retrieval_repo = RetrievalRepo(session)
            retrieval_row = await retrieval_repo.create(
                query_id=query_id,
                top_k=self._top_k,
                chunk_ids=[chunk["chunk_id"] for chunk in retrieved],
                similarities=[Decimal(str(chunk["similarity"])) for chunk in retrieved],
                embedding_model_version=self._embedder.model,
            )

            audit_writer = AuditWriter(
                audit_record_repo=AuditRecordRepo(session),
                node_invocation_repo=NodeInvocationRepo(session),
            )
            await audit_writer.write_node_invocation(
                query_id,
                node_name=self.name,
                started_at=started_at,
                finished_at=finished_at,
                model_identity=self.model_identity,
                model_version=self.model_version,
                processing_region=REGION_UNKNOWN,
                input_token_count=None,
                output_token_count=None,
            )
            await session.commit()

        state["retrieval_id"] = retrieval_row.id
        state["retrieved_chunks"] = retrieved
        return state


__all__ = ["DEFAULT_TOP_K", "RetrievalNode"]
