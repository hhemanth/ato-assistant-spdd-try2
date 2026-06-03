"""LangGraph topology for the ATO chat-turn pipeline (T046).

This module wires the eight-node topology declared in
``specs/001-ato-chat-rag/research.md``:

.. code-block:: text

    START
      → pii_node              (PII detection + mask/refuse — Agent 4, Slice 2)
      → scope_safety_node     (Rules + classifier — Agent 5, Slice 2)
      → retrieval_node        (Agent 1, retrieval half) — REAL (T040)
      → generation_node       (Agent 1, generation half) — REAL (T041)
      → citation_check_node   (Agent 3, Slice 2/3)
      → scoring_node          (Agent 2, US7)
      → finalize_node         (attach disclaimer + badge + audit) — REAL (T045)
    END

Any guard-bearing node (``pii_node``, ``scope_safety_node``,
``citation_check_node``, ``scoring_node``) may short-circuit the
pipeline by setting ``state["refusal"]``; the conditional edge
produced by :func:`~src.agents.refusal_router.make_refusal_router`
routes those turns to a single terminal ``refusal_node``.

T046 makes the three Slice 1 "real-call" nodes (``retrieval_node``,
``generation_node``, ``finalize_node``) the production implementations
landed in T040 / T041 / T045. The four guard nodes plus the terminal
``refusal_node`` stay as pass-through placeholders until their owning
slices land — they are wired into the topology so the conditional
edges have somewhere to route to.

A :class:`GraphDeps` value object collects every dependency the real
nodes need (DB session factory, embedder, retrieval client, Anthropic
client, audit writer surface, three region labels). Tests construct a
``GraphDeps`` with mocks; production wiring is via
:func:`build_default_graph` which lazily imports the heavy provider
SDKs (``anthropic``, ``voyageai``) so importing this module never
requires a live API key.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from .finalize_node import FinalizeNode, _observability_region_from_endpoint
from .generation.generation_node import GenerationNode
from .refusal_router import REFUSAL_NODE_NAME, make_refusal_router
from .retrieval.retrieval_node import RetrievalNode
from .state import ChatTurnState

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractAsyncContextManager

    from anthropic import AsyncAnthropic
    from sqlalchemy.ext.asyncio import AsyncSession

    from agents.retrieval.pgvector_client import PgVectorClient
    from ingestion.embedder.voyage_embedder import VoyageEmbedder


# ---------------------------------------------------------------------------
# Dependency value object
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GraphDeps:
    """Bundle of dependencies the real Slice 1 nodes need.

    A ``frozen`` dataclass so the graph builder can safely share a
    single ``GraphDeps`` across multiple ``build_graph`` invocations
    without worrying about mutation between calls.

    Attributes
    ----------
    session_factory:
        Zero-arg callable returning an :class:`AsyncSession` context
        manager. Used by ``retrieval_node``, ``generation_node``, and
        ``finalize_node`` for audit + entity writes.
    embedder:
        Voyage AI embedder (T038). Injected into ``retrieval_node``.
    retrieval_client:
        pgvector retrieval client (T039). Injected into ``retrieval_node``.
    anthropic_client:
        Pre-built :class:`anthropic.AsyncAnthropic`. Injected into
        ``generation_node``.
    processing_region_llm:
        Opaque region label for the LLM provider (Anthropic).
    processing_region_embedding:
        Opaque region label for the embedder provider (Voyage).
    processing_region_observability:
        Opaque region label for the observability provider (LangSmith).
    """

    session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]]
    embedder: VoyageEmbedder
    retrieval_client: PgVectorClient
    anthropic_client: AsyncAnthropic
    processing_region_llm: str
    processing_region_embedding: str
    processing_region_observability: str


# ---------------------------------------------------------------------------
# Placeholder nodes for the guard surfaces not yet implemented in Slice 1
# ---------------------------------------------------------------------------


class _PlaceholderNode:
    """Base for the pass-through guard nodes wired into the graph.

    The four guard nodes (``pii_node``, ``scope_safety_node``,
    ``citation_check_node``, ``scoring_node``) plus the terminal
    ``refusal_node`` land with later slices. Until they do, each is a
    no-op pass-through so the graph compiles and the Slice 1 happy
    path runs end-to-end.
    """

    name: str = "placeholder"
    model_identity: str | None = None
    model_version: str | None = None

    async def __call__(self, state: ChatTurnState) -> ChatTurnState:
        """No-op pass-through. Production logic lands in later slices."""
        return state


class _PIINode(_PlaceholderNode):
    name = "pii_node"


class _ScopeSafetyNode(_PlaceholderNode):
    name = "scope_safety_node"


class _CitationCheckNode(_PlaceholderNode):
    name = "citation_check_node"


class _ScoringNode(_PlaceholderNode):
    name = "scoring_node"


class _RefusalNode(_PlaceholderNode):
    name = REFUSAL_NODE_NAME


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


def _route_generation(state: ChatTurnState) -> str:
    """Conditional-edge router run after ``generation_node``.

    The generation node sets ``state["refusal"]`` when the model
    returns no usable answer (see T041 ``no-source`` path). Route
    to the terminal refusal node in that case; otherwise continue
    down the happy path to ``citation_check_node``.
    """
    if state.get("refusal") is not None:
        return REFUSAL_NODE_NAME
    return "citation_check_node"


def build_graph(
    deps: GraphDeps,
) -> CompiledStateGraph[ChatTurnState, None, ChatTurnState, ChatTurnState]:
    """Build and compile the chat-turn LangGraph using ``deps``.

    The three Slice 1 "real-call" nodes (``retrieval_node``,
    ``generation_node``, ``finalize_node``) are constructed inside
    this function from ``deps`` so callers can rebuild the graph with
    fresh mocks per test.

    Returns:
        A compiled :class:`langgraph.graph.state.CompiledStateGraph`
        ready for ``ainvoke`` / ``astream``.
    """
    # ---- Slice 1 real nodes ------------------------------------------------
    retrieval_node = RetrievalNode(
        embedder=deps.embedder,
        retrieval_client=deps.retrieval_client,
        session_factory=deps.session_factory,
    )
    generation_node = GenerationNode(
        client=deps.anthropic_client,
        session_factory=deps.session_factory,
        processing_region=deps.processing_region_llm,
    )
    finalize_node = FinalizeNode(
        session_factory=deps.session_factory,
        llm_region=deps.processing_region_llm,
        embedding_region=deps.processing_region_embedding,
        observability_region=deps.processing_region_observability,
    )

    # ---- Pass-through placeholders for later-slice guard nodes ------------
    pii_node = _PIINode()
    scope_safety_node = _ScopeSafetyNode()
    citation_check_node = _CitationCheckNode()
    scoring_node = _ScoringNode()
    refusal_node = _RefusalNode()

    g: StateGraph[ChatTurnState, None, ChatTurnState, ChatTurnState] = StateGraph(
        ChatTurnState,
    )

    # 1. Register every node before any edge references it.
    g.add_node(pii_node.name, pii_node)
    g.add_node(scope_safety_node.name, scope_safety_node)
    g.add_node(retrieval_node.name, retrieval_node)
    g.add_node(generation_node.name, generation_node)
    g.add_node(citation_check_node.name, citation_check_node)
    g.add_node(scoring_node.name, scoring_node)
    g.add_node(finalize_node.name, finalize_node)
    g.add_node(refusal_node.name, refusal_node)

    # 2. Happy-path entry + unconditional edges. ``retrieval_node`` cannot
    #    refuse on its own (any failure surfaces as an empty chunk list
    #    handled by ``generation_node``), so the retrieval → generation
    #    edge stays unconditional.
    g.add_edge(START, pii_node.name)
    g.add_edge(retrieval_node.name, generation_node.name)

    # 3. Conditional edges after every guard-bearing node. Each router
    #    closes over the next happy-path node so a refusal at any of
    #    these four boundaries jumps straight to ``refusal_node``.
    g.add_conditional_edges(
        pii_node.name,
        make_refusal_router(scope_safety_node.name),
        [scope_safety_node.name, refusal_node.name],
    )
    g.add_conditional_edges(
        scope_safety_node.name,
        make_refusal_router(retrieval_node.name),
        [retrieval_node.name, refusal_node.name],
    )
    g.add_conditional_edges(
        citation_check_node.name,
        make_refusal_router(scoring_node.name),
        [scoring_node.name, refusal_node.name],
    )
    g.add_conditional_edges(
        scoring_node.name,
        make_refusal_router(finalize_node.name),
        [finalize_node.name, refusal_node.name],
    )

    # 4. Generation has its own conditional edge — ``generation_node``
    #    sets ``state["refusal"]`` (reason ``no-source``) when no
    #    grounded answer is produced (T041). Route to refusal_node in
    #    that case; otherwise continue to ``citation_check_node``.
    g.add_conditional_edges(
        generation_node.name,
        _route_generation,
        [citation_check_node.name, refusal_node.name],
    )

    # 5. Terminal edges — both happy-path and refusal converge on END.
    g.add_edge(finalize_node.name, END)
    g.add_edge(refusal_node.name, END)

    return g.compile()


def build_default_graph() -> CompiledStateGraph[
    ChatTurnState, None, ChatTurnState, ChatTurnState
]:
    """Build the production graph from :func:`config.settings.get_settings`.

    Lazily imports :mod:`anthropic` and the embedder / retrieval client
    modules so importing :mod:`agents.graph` does not require the
    heavy provider SDKs at module-load time. This is the entry point
    the FastAPI ``/chat`` route uses; tests construct a custom
    :class:`GraphDeps` with mocked clients and call :func:`build_graph`
    directly.
    """
    # Local imports — keep the heavy SDKs out of the module-level graph.
    import anthropic  # noqa: PLC0415

    from agents.retrieval.pgvector_client import PgVectorClient  # noqa: PLC0415
    from config.settings import get_settings  # noqa: PLC0415
    from db.repos import get_sessionmaker  # noqa: PLC0415
    from ingestion.embedder.voyage_embedder import VoyageEmbedder  # noqa: PLC0415

    settings = get_settings()
    session_factory = get_sessionmaker()

    embedder = VoyageEmbedder(api_key=settings.voyage_api_key)
    retrieval_client = PgVectorClient(session_factory=session_factory)
    anthropic_client = anthropic.AsyncAnthropic(
        api_key=settings.anthropic_api_key.get_secret_value(),
    )

    deps = GraphDeps(
        session_factory=session_factory,
        embedder=embedder,
        retrieval_client=retrieval_client,
        anthropic_client=anthropic_client,
        processing_region_llm=settings.anthropic_region,
        processing_region_embedding="unknown",  # Voyage exposes no region
        processing_region_observability=_observability_region_from_endpoint(
            settings.langsmith_endpoint
        ),
    )
    return build_graph(deps)


__all__ = ["GraphDeps", "build_default_graph", "build_graph"]
