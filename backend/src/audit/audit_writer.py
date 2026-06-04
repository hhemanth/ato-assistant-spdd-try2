"""Per-turn audit writer (T018).

Records every user-facing turn per FR-017 (original masked prompt,
retrieval query, retrieved chunk IDs, model identity / version, rendered
answer or refusal reason, citation IDs, confidence and correctness
scores) and the three processing-region fields required by FR-018a
(``llm_region``, ``embedding_region``, ``observability_region``).

The actual database inserts are delegated to the typed repositories
created in T014 (:class:`db.repos.AuditRecordRepo`,
:class:`db.repos.NodeInvocationRepo`). This writer adds one layer of
defensive validation — the answer / refusal XOR is enforced fail-fast
in Python before the SQL CHECK constraint fires, with a clear error
message for the caller.

Region strings are opaque on purpose: provider regions differ in
naming (``ap-southeast-2``, ``ap-northeast-1``, ``us-east-1``, ...) and
the audit must record whatever the provider returns. When the region
cannot be detected at all, callers SHOULD pass :data:`REGION_UNKNOWN`
rather than an empty string so the audit row remains queryable.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from db.repos.audit_record import AuditRecord, AuditRecordRepo
from db.repos.node_invocation import NodeInvocation, NodeInvocationRepo

REGION_UNKNOWN: Final[str] = "unknown"
"""Sentinel for the processing-region columns when the upstream
provider does not expose a region. Persisting an explicit ``"unknown"``
keeps FR-018a's region columns NOT NULL-compatible and makes audit
queries (``WHERE llm_region = 'unknown'``) trivial."""


class AuditWriter:
    """Façade over the audit-record and node-invocation repositories.

    Construct one per request / unit-of-work. The writer holds typed
    repository instances; the parent (FastAPI request handler or
    LangGraph node) owns the underlying ``AsyncSession`` lifecycle.
    """

    def __init__(
        self,
        *,
        audit_record_repo: AuditRecordRepo,
        node_invocation_repo: NodeInvocationRepo,
    ) -> None:
        self._audit_record_repo = audit_record_repo
        self._node_invocation_repo = node_invocation_repo

    async def write_turn(  # noqa: PLR0913 — one keyword-only argument per audit column by design (FR-017 / FR-018a).
        self,
        query_id: uuid.UUID,
        *,
        answer_id: uuid.UUID | None = None,
        refusal_id: uuid.UUID | None = None,
        retrieval_id: uuid.UUID | None = None,
        langsmith_trace_id: str | None = None,
        llm_region: str,
        embedding_region: str,
        observability_region: str,
    ) -> AuditRecord:
        """Write the per-turn audit record.

        Exactly one of ``answer_id`` or ``refusal_id`` MUST be set —
        this mirrors the database CHECK constraint
        ``ck_audit_record_answer_xor_refusal`` and is enforced here
        first so callers get a clear Python-level error rather than a
        :class:`sqlalchemy.exc.IntegrityError` deep in the flush.
        """
        if (answer_id is None) == (refusal_id is None):
            msg = (
                "AuditWriter.write_turn requires exactly one of "
                "answer_id or refusal_id (FR-017 / data-model.md)."
            )
            raise ValueError(msg)
        return await self._audit_record_repo.write_turn(
            query_id=query_id,
            processing_region_llm=llm_region,
            processing_region_embedding=embedding_region,
            processing_region_observability=observability_region,
            answer_id=answer_id,
            refusal_id=refusal_id,
            retrieval_id=retrieval_id,
            langsmith_trace_id=langsmith_trace_id,
        )

    async def write_node_invocation(  # noqa: PLR0913 — one keyword-only argument per node_invocation column by design.
        self,
        query_id: uuid.UUID,
        *,
        node_name: str,
        started_at: datetime,
        finished_at: datetime,
        model_identity: str | None = None,
        model_version: str | None = None,
        processing_region: str | None = None,
        input_token_count: int | None = None,
        output_token_count: int | None = None,
    ) -> NodeInvocation:
        """Record a single LangGraph node invocation.

        Use for any node that calls a model (LLM, classifier,
        embedder). The repo validates ``node_name`` against the closed
        ``NODE_NAMES`` set so typos surface at write time, not at audit
        time.
        """
        return await self._node_invocation_repo.record(
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

    async def write_node_timing(
        self,
        query_id: uuid.UUID,
        *,
        node_name: str,
        started_at: datetime,
        finished_at: datetime,
    ) -> NodeInvocation:
        """Record a deterministic (model-free) node's timing.

        Convenience wrapper over :meth:`write_node_invocation` for the
        rules-only / pure-Python nodes (URL liveness check, refusal
        router, deterministic guard rules) where there is no model
        identity / region to capture but timing is still useful for
        end-to-end latency attribution (SC-008).
        """
        return await self._node_invocation_repo.record(
            query_id=query_id,
            node_name=node_name,
            started_at=started_at,
            finished_at=finished_at,
        )


__all__ = ["REGION_UNKNOWN", "AuditWriter"]
