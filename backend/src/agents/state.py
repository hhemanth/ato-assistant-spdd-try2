"""Typed shared LangGraph state for the ATO chat turn pipeline.

The :class:`ChatTurnState` ``TypedDict`` is the single value object
that flows through every node in the LangGraph topology defined in
``research.md`` (seven nodes: ``pii_node``, ``scope_safety_node``,
``retrieval_node``, ``generation_node``, ``citation_check_node``,
``scoring_node``, ``finalize_node``).

Fields are populated incrementally as nodes execute, so the outer
``TypedDict`` is declared with ``total=False``. Each inline value
object (``RetrievedChunk``, ``ProposedCitation``,
``VerifiedCitation``, ``RefusalState``) is ``total=True`` — when a
node emits one, every field is required.

This module deliberately uses only stdlib types (UUID, datetime,
Literal, TypedDict). It MUST NOT import from ``db.repos`` — keeping
the LangGraph state file free of SQLAlchemy mapped types preserves a
clean inter-node contract and avoids circular imports.

The enum literals here mirror the ``CHECK`` constraints in
``data-model.md``:

* ``RefusalReasonCode`` — 10 values from ``refusal.reason_code``
  (line 179).
* ``ProducedByNode`` — 6 values from ``refusal.produced_by_node``
  (line 182). NOTE: this is intentionally narrower than the 9 values
  on ``node_invocation.node_name`` — only nodes that can refuse
  appear here.
* ``PIIOutcome``, ``ScopeVerdict``, ``LivenessStatus``,
  ``ConfidenceBand`` — mirror their respective columns.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, TypedDict
from uuid import UUID

PIIOutcome = Literal["clean", "masked", "refused"]
"""Outcome of the PII detection/masking step (``query.pii_outcome``)."""

ScopeVerdict = Literal[
    "in_scope",
    "out_of_scope",
    "inappropriate",
    "personal_advice",
    "non_english",
]
"""Verdict from the scope/safety classifier (rules + dedicated model)."""

LivenessStatus = Literal["live", "stale", "unknown"]
"""Source-liveness verdict from the citation-check node
(``citation.liveness_status``)."""

ConfidenceBand = Literal["high", "medium", "low"]
"""User-facing confidence-badge bucket (``answer.confidence_band``)."""

RefusalReasonCode = Literal[
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
]
"""All ten refusal reasons (``refusal.reason_code``)."""

ProducedByNode = Literal[
    "pii_node",
    "scope_safety_node",
    "retrieval_node",
    "generation_node",
    "citation_check_node",
    "scoring_node",
]
"""Nodes that can produce a refusal (``refusal.produced_by_node``).

Narrower than ``node_invocation.node_name`` — ``finalize_node`` and
the auxiliary classifier sub-nodes never originate refusals.
"""


class RetrievedChunk(TypedDict):
    """One retrieved chunk emitted by ``retrieval_node``.

    Mirrors the projection the generation node needs: the chunk id,
    its source URL, a snippet to ground the answer in, the cosine
    similarity from the vector search, and the source page's
    ``Last-Modified`` timestamp when available (``None`` when the
    upstream page did not advertise one).
    """

    chunk_id: UUID
    source_url: str
    snippet: str
    similarity: float
    source_last_modified: datetime | None


class ProposedCitation(TypedDict):
    """A citation as proposed by ``generation_node``.

    ``index`` is the 1-based footnote index as rendered in the
    answer text. ``anchor`` is an optional URL fragment when the
    citation targets a sub-section of the source page.
    """

    index: int
    source_url: str
    anchor: str | None


class VerifiedCitation(ProposedCitation):
    """A proposed citation after ``citation_check_node`` verifies it.

    Extends :class:`ProposedCitation` with the source-liveness
    verdict from the citation-check node.
    """

    liveness_status: LivenessStatus


class RefusalState(TypedDict):
    """Refusal payload attached to ``ChatTurnState`` when any node's
    guard fails.

    The presence of this key in :class:`ChatTurnState` short-circuits
    downstream nodes and routes the turn to ``refusal_node`` →
    ``finalize_node`` per the topology in ``research.md``.
    """

    reason_code: RefusalReasonCode
    user_message: str
    produced_by_node: ProducedByNode


class ChatTurnState(TypedDict, total=False):
    """Shared LangGraph state for one chat turn.

    Fields are populated incrementally as nodes execute. The outer
    ``TypedDict`` is ``total=False`` so a node may read or write any
    subset. The first four fields (``query_id``, ``session_id``,
    ``original_text``, ``received_at``) are populated at graph entry
    and SHOULD be present in every downstream node.
    """

    # Populated at graph entry.
    query_id: UUID
    session_id: UUID
    original_text: str
    received_at: datetime

    # Populated by ``pii_node``.
    masked_text: str
    pii_detected: list[str]
    pii_outcome: PIIOutcome

    # Populated by ``scope_safety_node``.
    scope_verdict: ScopeVerdict
    scope_confidence: float

    # Populated by ``retrieval_node``.
    retrieval_id: UUID
    retrieved_chunks: list[RetrievedChunk]

    # Populated by ``generation_node``.
    generated_text: str
    proposed_citations: list[ProposedCitation]

    # Populated by ``citation_check_node``.
    verified_citations: list[VerifiedCitation]

    # Populated by ``scoring_node``.
    confidence: float | None
    correctness: float | None
    confidence_band: ConfidenceBand | None

    # Populated whenever a node's guard fails.
    refusal: RefusalState
