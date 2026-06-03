"""Finalize LangGraph node (T045).

The finalize node is the terminal happy-path node — it converts the
in-memory :class:`agents.state.ChatTurnState` into the persistent rows
that back the API response and the audit log:

1. ``answer`` row capturing the rendered text, the generation-side
   parameters, the per-answer disclaimer version, and (NULL for Slice
   1) the scoring columns — those are populated by the scoring node
   in US7.
2. One ``citation`` row per proposed citation. For Slice 1 every row
   carries ``liveness_status='unknown'`` because the dedicated
   citation-check node (T043) lands with US3 / liveness verification.
3. ``audit_record`` row linking the ``answer``, ``retrieval``, and
   ``query`` together with the three FR-018a processing-region fields.

The node also writes :attr:`ChatTurnState.verified_citations` (with
``liveness_status='unknown'`` per Slice 1's convention) so the
downstream API serialization layer (T047) can build the response
without re-querying the DB.

Per-answer disclaimer
=====================

The disclaimer text (FR-003) is *not* baked into the answer body — it
travels alongside the answer in the response payload's
``per_answer_disclaimer`` field. The answer row stores only the
:data:`disclaimers.templates.DISCLAIMER_VERSION` so the audit log can
pin the exact wording per turn.

Region attribution
==================

* ``processing_region_llm`` — from
  :attr:`config.settings.Settings.anthropic_region` (defaults to
  ``"us-east-1"``).
* ``processing_region_embedding`` —
  :data:`audit.audit_writer.REGION_UNKNOWN`; Voyage's HTTP response
  does not advertise a region.
* ``processing_region_observability`` — hostname of
  :attr:`config.settings.Settings.langsmith_endpoint` when set
  (regional endpoints encode the region in the host, e.g.
  ``apac.api.smith.langchain.com``), else ``"us"`` as the LangSmith
  default.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlparse

from audit.audit_writer import REGION_UNKNOWN, AuditWriter
from db.repos.answer import AnswerRepo
from db.repos.audit_record import AuditRecordRepo
from db.repos.citation import CitationInput, CitationRepo
from db.repos.node_invocation import NodeInvocationRepo
from disclaimers.templates import DISCLAIMER_VERSION

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractAsyncContextManager

    from sqlalchemy.ext.asyncio import AsyncSession

    from agents.state import ChatTurnState, RetrievedChunk, VerifiedCitation


#: Liveness status applied to every Slice 1 citation. The dedicated
#: liveness-check node (T043) replaces this with ``"live"`` / ``"stale"``
#: when US3 lands; until then ``"unknown"`` is the truthful label.
SLICE1_LIVENESS_STATUS: Literal["unknown"] = "unknown"

#: Default observability region label when no LangSmith endpoint is set
#: (LangSmith's primary cluster is US-hosted).
DEFAULT_OBSERVABILITY_REGION: str = "us"


def _observability_region_from_endpoint(endpoint: str | None) -> str:
    """Derive an opaque region label from a LangSmith endpoint URL.

    The regional endpoints encode the region in the host (e.g.
    ``apac.api.smith.langchain.com`` → ``"apac"``,
    ``eu.api.smith.langchain.com`` → ``"eu"``); the default endpoint is
    US so ``None`` collapses to :data:`DEFAULT_OBSERVABILITY_REGION`.
    """
    if not endpoint:
        return DEFAULT_OBSERVABILITY_REGION
    host = urlparse(endpoint).hostname or ""
    leading = host.split(".", 1)[0] if host else ""
    return leading or DEFAULT_OBSERVABILITY_REGION


def _chunk_id_by_source_url(
    chunks: list[RetrievedChunk],
) -> dict[str, tuple[Any, RetrievedChunk]]:
    """Index retrieved chunks by ``source_url`` for citation linkage.

    Returns a ``url -> (chunk_id, chunk)`` map; later citations targeting
    the same URL collapse to the first chunk encountered, mirroring how
    the generation prompt numbers sources.
    """
    out: dict[str, tuple[Any, RetrievedChunk]] = {}
    for chunk in chunks:
        url = chunk["source_url"]
        if url not in out:
            out[url] = (chunk["chunk_id"], chunk)
    return out


class FinalizeNode:
    """LangGraph node implementing ``finalize_node`` (T045).

    Satisfies :class:`agents.node_protocol.NodeProtocol`. Pure-Python +
    DB writes — no model call, so ``model_identity`` and
    ``model_version`` are ``None``.

    Parameters
    ----------
    session_factory:
        Async-session context-manager factory. The node opens a single
        session so the ``answer``, ``citation``, and ``audit_record``
        writes land in the same transaction.
    llm_region:
        Opaque region label for the LLM call, forwarded to
        ``audit_record.processing_region_llm``.
    embedding_region:
        Opaque region label for the embedder call. Defaults to
        :data:`audit.audit_writer.REGION_UNKNOWN`.
    observability_region:
        Opaque region label for the observability provider. Defaults to
        :data:`DEFAULT_OBSERVABILITY_REGION`.
    """

    name: str = "finalize_node"
    model_identity: str | None = None
    model_version: str | None = None

    def __init__(
        self,
        *,
        session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
        llm_region: str,
        embedding_region: str = REGION_UNKNOWN,
        observability_region: str = DEFAULT_OBSERVABILITY_REGION,
    ) -> None:
        self._session_factory = session_factory
        self._llm_region = llm_region
        self._embedding_region = embedding_region
        self._observability_region = observability_region

    async def __call__(self, state: ChatTurnState) -> ChatTurnState:
        """Persist answer/citations/audit and stash verified citations on state."""

        from agents.state import VerifiedCitation  # noqa: PLC0415

        query_id = state["query_id"]
        retrieval_id = state["retrieval_id"]
        answer_text = state["generated_text"]
        proposed_citations = state.get("proposed_citations") or []
        chunks = state.get("retrieved_chunks") or []

        chunk_lookup = _chunk_id_by_source_url(chunks)

        started_at = datetime.now(tz=UTC)
        async with self._session_factory() as session:
            answer_repo = AnswerRepo(session)
            citation_repo = CitationRepo(session)
            audit_writer = AuditWriter(
                audit_record_repo=AuditRecordRepo(session),
                node_invocation_repo=NodeInvocationRepo(session),
            )

            # Scoring columns are intentionally NULL — US7 lands the
            # scoring node + a migration that backfills them.
            answer_row = await answer_repo.create(
                query_id=query_id,
                retrieval_id=retrieval_id,
                text_value=answer_text,
                model_identity="claude-sonnet-4-6",
                model_version="2026-01",
                generation_params={"max_tokens": 1024},
                per_answer_disclaimer_version=DISCLAIMER_VERSION,
                confidence_score=None,
                correctness_score=None,
                confidence_band=None,
            )

            citation_inputs: list[CitationInput] = []
            verified: list[VerifiedCitation] = []
            for proposed in proposed_citations:
                url = proposed["source_url"]
                lookup = chunk_lookup.get(url)
                if lookup is None:
                    # The generation node may have surfaced a URL that
                    # didn't make it into the retrieved chunks (e.g.
                    # text-mode parsing of a malformed reference line).
                    # Skip rather than write an orphan citation row.
                    continue
                chunk_id, chunk = lookup
                citation_inputs.append(
                    CitationInput(
                        chunk_id=chunk_id,
                        source_url=url,
                        snippet=chunk["snippet"],
                        liveness_status=SLICE1_LIVENESS_STATUS,
                        anchor=proposed.get("anchor"),
                        source_last_modified_at_cite=chunk.get(
                            "source_last_modified"
                        ),
                        liveness_checked_at=None,
                    )
                )
                verified.append(
                    VerifiedCitation(
                        index=proposed["index"],
                        source_url=url,
                        anchor=proposed.get("anchor"),
                        liveness_status=SLICE1_LIVENESS_STATUS,
                    )
                )

            if citation_inputs:
                await citation_repo.create_many(
                    answer_id=answer_row.id, citations=citation_inputs
                )

            finished_at = datetime.now(tz=UTC)
            await audit_writer.write_node_timing(
                query_id,
                node_name=self.name,
                started_at=started_at,
                finished_at=finished_at,
            )

            await audit_writer.write_turn(
                query_id,
                answer_id=answer_row.id,
                retrieval_id=retrieval_id,
                llm_region=self._llm_region,
                embedding_region=self._embedding_region,
                observability_region=self._observability_region,
            )

        state["verified_citations"] = verified
        return state


__all__ = [
    "DEFAULT_OBSERVABILITY_REGION",
    "SLICE1_LIVENESS_STATUS",
    "FinalizeNode",
    "_observability_region_from_endpoint",
]
