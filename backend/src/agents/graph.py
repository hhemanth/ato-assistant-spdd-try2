"""LangGraph topology for the ATO chat-turn pipeline.

This module wires the eight-node topology declared in
``specs/001-ato-chat-rag/research.md``:

.. code-block:: text

    START
      → pii_node              (PII detection + mask/refuse — Agent 4)
      → scope_safety_node     (Rules + classifier — Agent 5)
      → retrieval_node        (Agent 1, retrieval half)
      → generation_node       (Agent 1, generation half)
      → citation_check_node   (Agent 3)
      → scoring_node          (Agent 2)
      → finalize_node         (attach disclaimer + badge + audit)
    END

Any guard-bearing node (``pii_node``, ``scope_safety_node``,
``citation_check_node``, ``scoring_node``) may short-circuit the
pipeline by setting ``state["refusal"]``; the conditional edge
produced by :func:`~src.agents.refusal_router.make_refusal_router`
routes those turns to a single terminal ``refusal_node``.

This file ships **placeholder** node implementations: each is a small
class satisfying :class:`~src.agents.node_protocol.NodeProtocol`
(``name`` / ``model_identity`` / ``model_version`` class attrs plus an
async ``__call__``) that returns the state unchanged. Phase 3+ tasks
replace each placeholder with the production node implementation; the
graph topology and edge wiring here stays put. See T046 for the
swap-in.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from .refusal_router import REFUSAL_NODE_NAME, make_refusal_router
from .state import ChatTurnState


class _PlaceholderNode:
    """Base for the eight placeholder nodes wired into the graph.

    Holds the class-level attrs required by
    :class:`~src.agents.node_protocol.NodeProtocol` and a no-op async
    ``__call__`` that returns the state unchanged. Subclasses override
    only ``name`` (and, where appropriate, ``model_identity`` /
    ``model_version``).

    These placeholders exist so the graph can be **compiled and
    introspected today**, before any node author lands real logic.
    They are replaced wholesale by T046.
    """

    name: str = "placeholder"
    model_identity: str | None = None
    model_version: str | None = None

    async def __call__(self, state: ChatTurnState) -> ChatTurnState:
        """No-op pass-through. Production logic lands in Phase 3+."""
        return state


class _PIINode(_PlaceholderNode):
    name = "pii_node"


class _ScopeSafetyNode(_PlaceholderNode):
    name = "scope_safety_node"


class _RetrievalNode(_PlaceholderNode):
    name = "retrieval_node"


class _GenerationNode(_PlaceholderNode):
    name = "generation_node"


class _CitationCheckNode(_PlaceholderNode):
    name = "citation_check_node"


class _ScoringNode(_PlaceholderNode):
    name = "scoring_node"


class _FinalizeNode(_PlaceholderNode):
    name = "finalize_node"


class _RefusalNode(_PlaceholderNode):
    name = REFUSAL_NODE_NAME


# Module-level singletons — LangGraph captures the callable in
# ``add_node``; one instance per node keeps introspection (``g.nodes``)
# stable across ``build_graph`` invocations.
pii_node = _PIINode()
scope_safety_node = _ScopeSafetyNode()
retrieval_node = _RetrievalNode()
generation_node = _GenerationNode()
citation_check_node = _CitationCheckNode()
scoring_node = _ScoringNode()
finalize_node = _FinalizeNode()
refusal_node = _RefusalNode()


def build_graph() -> CompiledStateGraph[ChatTurnState, None, ChatTurnState, ChatTurnState]:
    """Build and compile the chat-turn LangGraph.

    Registers all eight placeholder nodes (the seven happy-path nodes
    plus the terminal ``refusal_node``), wires the linear happy-path
    edges, and attaches conditional refusal-routing edges after each
    guard-bearing node via
    :func:`~src.agents.refusal_router.make_refusal_router`.

    Returns:
        A compiled :class:`langgraph.graph.state.CompiledStateGraph`
        ready for ``ainvoke`` / ``astream``. The compiled graph
        exposes ``.nodes`` for introspection (used by the build smoke
        test in tasks.md).
    """
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

    # 2. Happy-path entry + unconditional edges for nodes that have no
    #    refusal hand-off (retrieval and generation cannot refuse per
    #    ``state.ProducedByNode`` minus the four guard nodes).
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

    # 4. Generation → citation_check is unconditional (generation
    #    cannot refuse on its own; any citation issue surfaces in
    #    ``citation_check_node``).
    g.add_edge(generation_node.name, citation_check_node.name)

    # 5. Terminal edges — both happy-path and refusal converge on END.
    g.add_edge(finalize_node.name, END)
    g.add_edge(refusal_node.name, END)

    return g.compile()


__all__ = ["build_graph"]
