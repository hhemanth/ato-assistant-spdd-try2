"""Refusal routing helper for the LangGraph chat-turn topology.

Every guard-bearing node (``pii_node``, ``scope_safety_node``,
``citation_check_node``, ``scoring_node``) writes a ``refusal``
payload onto :class:`~src.agents.state.ChatTurnState` when its guard
fails. The conditional edge produced by :func:`make_refusal_router`
inspects that key after each such node and routes the turn to
``refusal_node`` (terminal) when set, or to the next happy-path node
otherwise.

The factory pattern keeps the router *pure* and trivially
unit-testable while letting one helper serve every conditional edge
in the graph — the only thing that varies between call sites is the
name of the next-on-success node.

Example::

    g.add_conditional_edges(
        "pii_node",
        make_refusal_router("scope_safety_node"),
    )

Both ``make_refusal_router`` and the constant
:data:`REFUSAL_NODE_NAME` are re-exported so graph wiring code never
has to hard-code the string ``"refusal_node"``.
"""

from __future__ import annotations

from collections.abc import Callable

from .state import ChatTurnState

REFUSAL_NODE_NAME: str = "refusal_node"
"""Stable name of the terminal refusal node in the LangGraph topology.

Centralised here so neither graph-builder code nor tests have to
duplicate the literal.
"""


def make_refusal_router(
    next_on_success: str,
) -> Callable[[ChatTurnState], str]:
    """Build a conditional-edge router for a single source node.

    The returned closure is pure: it inspects ``state["refusal"]`` and
    returns either :data:`REFUSAL_NODE_NAME` (when a refusal payload is
    present) or ``next_on_success`` (the next node in the happy-path
    topology for the source node this router is attached to).

    Args:
        next_on_success: Name of the node to route to when no refusal
            is set. Must match a node registered on the
            :class:`langgraph.graph.StateGraph`.

    Returns:
        A pure ``(state) -> node_name`` callable suitable for passing
        to :meth:`langgraph.graph.StateGraph.add_conditional_edges`.
    """

    def _route(state: ChatTurnState) -> str:
        # ``ChatTurnState`` is ``total=False``; ``.get`` returns ``None``
        # when no upstream node has set a refusal payload.
        if state.get("refusal") is not None:
            return REFUSAL_NODE_NAME
        return next_on_success

    return _route


__all__ = ["REFUSAL_NODE_NAME", "make_refusal_router"]
