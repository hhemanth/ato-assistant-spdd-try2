"""``POST /chat`` route (T047).

Receives a :class:`ChatRequest`, invokes the production LangGraph
assembled by :func:`agents.graph.build_default_graph`, and returns
either an :class:`AnswerResponse` (200, ``kind="answer"``) or a
:class:`RefusalResponse` (200, ``kind="refusal"``). Both responses
travel as HTTP 200 per the OpenAPI contract — a *refusal* is a typed
domain value, not an HTTP error.

Graph injection seam
====================

Production wires the default graph lazily on the first request (via
:func:`_get_graph`); the singleton is cached for the process lifetime.
Tests replace the graph wholesale by calling
:func:`set_graph_for_tests` with a graph built from a
:class:`agents.graph.GraphDeps` that injects mocked clients.

This keeps the production code path untouched while letting test
fixtures bind the graph's session factory to a transactional rollback
session and swap in respx-mocked Anthropic + Voyage clients.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal, cast
from uuid import uuid4

from fastapi import APIRouter

from .models import (
    AnswerResponse,
    ChatRequest,
    ChatResponse,
    Citation,
    RefusalResponse,
)

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

    from agents.state import ChatTurnState


#: Module-level cache for the production graph. Wrapping the slot in a
#: single-key dict avoids the ruff PLW0603 "discouraged use of global"
#: rule while keeping the same semantics: the value lives at module
#: scope so the FastAPI app and the test seam share one cache.
_graph_cache: dict[str, CompiledStateGraph[ChatTurnState, None, ChatTurnState, ChatTurnState]] = {}


def _get_graph() -> CompiledStateGraph[ChatTurnState, None, ChatTurnState, ChatTurnState]:
    """Return the cached production graph; build on first use."""
    graph = _graph_cache.get("graph")
    if graph is None:
        # Local import — keeps the heavy SDK imports out of module load.
        from agents.graph import build_default_graph  # noqa: PLC0415

        graph = build_default_graph()
        _graph_cache["graph"] = graph
    return graph


def set_graph_for_tests(
    graph: CompiledStateGraph[ChatTurnState, None, ChatTurnState, ChatTurnState] | None,
) -> None:
    """Test-only seam: replace the cached graph with a custom one.

    Pass ``None`` to clear the cache and force the next request to
    rebuild via :func:`agents.graph.build_default_graph`.
    """
    if graph is None:
        _graph_cache.pop("graph", None)
    else:
        _graph_cache["graph"] = graph


chat_router = APIRouter()


#: Slice 1 default confidence band. The scoring node (US7 / T133)
#: replaces this with the real banded score; until then we surface
#: ``"high"`` because the only path that reaches this code is the
#: cited-answer happy path (citation-misaligned / no-source turns
#: take the refusal branch).
_SLICE1_CONFIDENCE_BAND: Literal["high", "medium", "low"] = "high"

#: Fallback model identity used when the LangGraph state does not
#: carry one. Production callers MUST land a generation-node-supplied
#: identity here; this string is the contracted Slice 1 default.
_DEFAULT_MODEL_IDENTITY: str = "claude-sonnet-4-6"


@chat_router.post(
    "/chat",
    response_model=ChatResponse,
    operation_id="postChat",
    tags=["chat"],
    summary="Ask a question. Returns a cited answer or a refusal.",
)
async def post_chat(request: ChatRequest) -> ChatResponse:
    """Drive the chat turn through the LangGraph and shape the response.

    Refusals (typed domain values surfaced by the guard nodes) round-trip
    as 200 ``kind="refusal"`` per the OpenAPI contract.
    """

    # Local imports — keep the per-answer disclaimer module off the
    # import-time graph so this module loads without ``disclaimers``
    # in unrelated environments (e.g. metadata-only tooling).
    from disclaimers.templates import PER_ANSWER  # noqa: PLC0415

    # The query row is created by the pii_node (T070, currently the
    # Slice 1 stub in `agents.graph._Slice1PiiStub`); the final
    # ``state["query_id"]`` is the canonical id everything else FKs to.
    # We seed with a transient uuid that the pii_node overwrites.
    initial_state: ChatTurnState = {
        "query_id": uuid4(),
        "session_id": request.session_id,
        "original_text": request.text,
        "received_at": datetime.now(tz=UTC),
    }

    graph = _get_graph()
    raw_result = await graph.ainvoke(initial_state)
    # LangGraph returns the final merged state as a plain dict typed
    # as ChatTurnState. Cast for downstream type checking; ``.get``
    # access works either way.
    result = cast("ChatTurnState", raw_result)
    # Authoritative id is whatever the pii_node wrote into the DB.
    query_id = result["query_id"]

    refusal = result.get("refusal")
    if refusal is not None:
        return RefusalResponse(
            query_id=query_id,
            reason_code=refusal["reason_code"],
            user_message=refusal["user_message"],
            refused_at=datetime.now(tz=UTC),
        )

    # Happy-path answer. The finalize node populates
    # ``verified_citations``; the generation node populates
    # ``generated_text``. We synthesise the API-facing Citation list by
    # joining verified citations to the retrieved chunks (which carry
    # the snippet + source_last_modified the contract requires).
    chunks_by_url: dict[str, dict[str, object]] = {}
    for chunk in result.get("retrieved_chunks") or []:
        url = str(chunk["source_url"])
        if url not in chunks_by_url:
            chunks_by_url[url] = {
                "snippet": chunk["snippet"],
                "source_last_modified": chunk["source_last_modified"],
            }

    citations: list[Citation] = []
    for verified in result.get("verified_citations") or []:
        url = verified["source_url"]
        chunk_meta = chunks_by_url.get(url, {})
        snippet_value = chunk_meta.get("snippet", "")
        last_mod_value = chunk_meta.get("source_last_modified")
        citations.append(
            Citation(
                index=verified["index"],
                source_url=url,
                anchor=verified.get("anchor"),
                snippet=str(snippet_value),
                source_last_modified=cast("datetime | None", last_mod_value),
                liveness_status=verified["liveness_status"],
            )
        )

    return AnswerResponse(
        query_id=query_id,
        text=result.get("generated_text") or "",
        citations=citations,
        confidence_band=_SLICE1_CONFIDENCE_BAND,
        per_answer_disclaimer=PER_ANSWER,
        model_identity=_DEFAULT_MODEL_IDENTITY,
        generated_at=datetime.now(tz=UTC),
    )


__all__ = ["chat_router", "set_graph_for_tests"]
