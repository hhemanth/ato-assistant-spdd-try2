"""Typed protocol for LangGraph nodes (Principle III: every node is a
testable, swappable unit with an explicit contract).

Each node in the LangGraph topology implements :class:`NodeProtocol`:
it exposes ``name``, ``model_identity`` / ``model_version`` (both
optional — ``None`` for deterministic-only nodes that make no model
call), and is callable as ``async def __call__(state) -> state``.

This module also declares the contract for the audit-writer helper
that nodes invoke at exit to record a ``node_invocation`` row
(Principle V transparency posture: every model call is logged with
its identity, version, region, and timing). The concrete
implementation lives in the audit writer module landed by T018;
this Protocol exists so T018's writer and every node author share
the same keyword-argument shape.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from .state import ChatTurnState


class NodeProtocol(Protocol):
    """Contract every LangGraph node in this codebase implements.

    Attributes are class-level (one per node implementation, not per
    instance) so a graph-builder can introspect them without
    instantiating the node:

    * ``name`` — stable identifier used for tracing and the
      ``node_invocation.node_name`` audit row.
    * ``model_identity`` — provider model id (e.g. ``claude-sonnet-4-6``,
      ``voyage-3-large``). ``None`` for deterministic-only nodes.
    * ``model_version`` — provider-pinned version. ``None`` for
      deterministic-only nodes.

    The ``__call__`` is async so nodes can await I/O (LLM calls, DB
    queries) without blocking the event loop. It returns the
    (possibly mutated) :class:`ChatTurnState`; LangGraph's reducer
    handles merging.
    """

    name: str
    model_identity: str | None
    model_version: str | None

    async def __call__(self, state: ChatTurnState) -> ChatTurnState:
        """Run the node against ``state`` and return the next state."""
        ...


class RecordNodeInvocation(Protocol):
    """Contract for the audit writer T018 will implement.

    Every node calls this at exit so the ``node_invocation`` table
    captures who-ran-what-when for every model call (Principle V).
    Deterministic-only nodes MAY skip the call or invoke it with
    ``model_identity=None`` / ``model_version=None`` to capture
    timing only.

    The keyword arguments mirror the columns of the
    ``node_invocation`` table in ``data-model.md``; T018's concrete
    writer MUST match this signature exactly.
    """

    # The keyword-only argument count mirrors the columns of the
    # ``node_invocation`` table one-for-one (data-model.md). Collapsing
    # them into a single bundle object would weaken the contract that
    # T018's writer is expected to match column-by-column.
    async def __call__(  # noqa: PLR0913 — see comment above
        self,
        *,
        query_id: UUID,
        node_name: str,
        started_at: datetime,
        finished_at: datetime,
        model_identity: str | None,
        model_version: str | None,
        processing_region: str | None,
        input_token_count: int | None,
        output_token_count: int | None,
    ) -> None:
        """Persist a single ``node_invocation`` row."""
        ...
