"""Generation LangGraph node (T041).

The generation node turns the retrieved chunks into a grounded answer
plus a structured citation list. It calls Claude Sonnet 4.6 via the
Anthropic Messages API using the **tool-use idiom** — Anthropic's
documented mechanism for forcing a model into a typed JSON response.

Why tool-use over free-form JSON?
=================================

The Messages API's ``tools`` + ``tool_choice`` parameters let us pin
the response to a single tool (``cite_answer``) whose input schema
declares the exact shape we need:

* ``answer`` — the rendered text, MUST contain inline ``[N]`` markers
  matching the citation list.
* ``citations`` — array of ``{index, source_url, snippet}`` records, one
  per ``[N]`` marker.

Tool-use guarantees a structured response without prompt-injection
risk, and the SDK exposes the parsed JSON in
``ToolUseBlock.input`` for type-safe extraction.

Text-mode fallback
==================

The test suite's :mod:`tests.conftest` mocks Anthropic with a plain
text response (``content=[{type: "text", text: "...[1]...[1] URL"}]``)
because the mock predates the tool-use upgrade. The response parser
in :func:`_parse_response` therefore prefers a ``tool_use`` block when
present (production posture) but falls back to text-mode parsing that
extracts ``[N]`` markers and a trailing ``[N] <url>`` reference table.
This keeps T028's mocked-Anthropic integration test working while the
production path uses the strict tool-use shape.

Refusal handling
================

If the model returns no usable answer (no ``[N]`` markers OR no
parseable citations OR the structured tool call signals an empty
answer), the node sets ``state["refusal"]`` with reason code
``no-source``. The conditional-edge router (T046) then routes the turn
to ``refusal_node``. This is the *only* refusal path the generation
node owns in Slice 1 — alignment checks (FR-013) land in the
``citation_check_node`` in a later slice.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from audit.audit_writer import AuditWriter
from db.repos.audit_record import AuditRecordRepo
from db.repos.node_invocation import NodeInvocationRepo

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractAsyncContextManager

    from anthropic import AsyncAnthropic
    from anthropic.types import ToolChoiceToolParam, ToolParam
    from sqlalchemy.ext.asyncio import AsyncSession

    from agents.state import (
        ChatTurnState,
        ProposedCitation,
        RetrievedChunk,
    )


#: Anthropic model identifier — pinned to the Sonnet 4.6 family per the
#: spec. The string MUST match the ``Message.model`` value the
#: integration-test mock returns so the audit row's identity field
#: round-trips cleanly.
MODEL_IDENTITY: str = "claude-sonnet-4-6"

#: Provider-pinned version. Anthropic's Messages API echoes the model
#: id back as ``Message.model`` but does not expose a distinct version
#: string; we record a stable label here so the audit log carries an
#: explicit version pointer (bump when the pinned model changes).
MODEL_VERSION: str = "2026-01"

#: Maximum tokens generated per call. Sized for a short cited answer
#: (the per-answer disclaimer is appended downstream, not generated).
DEFAULT_MAX_TOKENS: int = 1024

#: Inline-citation marker pattern — ``[1]``, ``[2]``, ..., ``[10]``,
#: etc. Used both for the *empty-answer* check and the text-mode
#: fallback parser.
_CITE_MARKER_RE: re.Pattern[str] = re.compile(r"\[(\d+)\]")

#: Trailing reference-line pattern: ``[N] https://www.ato.gov.au/...``.
#: Matches one line per citation in the text-mode fallback.
_REFERENCE_LINE_RE: re.Pattern[str] = re.compile(
    r"\[(\d+)\]\s+(https?://\S+)",
)


SYSTEM_PROMPT: str = (
    "You are the ATO Assistant answering Australian tax questions "
    "using ONLY the provided ATO sources. Every factual claim MUST "
    "cite a numbered source via [N] inline, matching the citations "
    'list. If the sources do not cover the question, return '
    '`{ "answer": "", "citations": [] }`.'
)


# Tool schema fed to Anthropic's ``tools`` parameter. The shape mirrors
# the dispatch's design choice 4 — one tool, one structured output. The
# value is a plain ``dict`` typed as :class:`anthropic.types.ToolParam`
# at the call site below so the SDK's overload picks the right variant.
_CITE_ANSWER_TOOL_DICT: dict[str, Any] = {
    "name": "cite_answer",
    "description": (
        "Return the grounded answer plus the citation list. The answer "
        "MUST embed [N] markers matching the citations array."
    ),
    "input_schema": {
        "type": "object",
        "required": ["answer", "citations"],
        "properties": {
            "answer": {
                "type": "string",
                "description": (
                    "Rendered answer with inline [N] citation markers. "
                    "Empty string when no source covers the question."
                ),
            },
            "citations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["index", "source_url", "snippet"],
                    "properties": {
                        "index": {
                            "type": "integer",
                            "minimum": 1,
                            "description": (
                                "1-based footnote index matching a [N] "
                                "marker in the answer text."
                            ),
                        },
                        "source_url": {
                            "type": "string",
                            "pattern": r"^https://www\.ato\.gov\.au/",
                            "description": "Source URL from the provided list.",
                        },
                        "snippet": {
                            "type": "string",
                            "description": "Short grounding snippet.",
                        },
                    },
                },
            },
        },
    },
}


def _build_user_message(
    masked_query: str, chunks: list[RetrievedChunk]
) -> str:
    """Render the user message — the masked query plus a numbered list
    of retrieved chunks.

    Indexes here are 1-based so the model's ``[N]`` markers line up
    with the entries in this list directly. The downstream finalize
    node maps these back onto chunk ids via ``source_url`` lookup.
    """

    lines: list[str] = [f"User question: {masked_query}", "", "Sources:"]
    for i, chunk in enumerate(chunks, start=1):
        lines.append(f"[{i}] {chunk['source_url']}\n{chunk['snippet']}")
    return "\n".join(lines)


def _parse_tool_use_block(
    block: Any,
) -> tuple[str, list[ProposedCitation]]:
    """Pull the typed ``{answer, citations}`` payload out of a ``cite_answer``
    tool-use block.

    Dedups citations by ``index`` preserving first occurrence. Silently
    skips malformed citation entries rather than failing the turn —
    callers treat an empty result as ``no-source``.
    """

    from agents.state import ProposedCitation  # noqa: PLC0415

    tool_input = getattr(block, "input", None) or {}
    answer_text = str(tool_input.get("answer", "")).strip()
    raw_citations = tool_input.get("citations") or []

    proposed: list[ProposedCitation] = []
    seen_indices: set[int] = set()
    for cite in raw_citations:
        if not isinstance(cite, dict):
            continue
        try:
            idx = int(cite["index"])
            url = str(cite["source_url"])
        except (KeyError, TypeError, ValueError):
            continue
        if idx in seen_indices:
            continue
        seen_indices.add(idx)
        proposed.append(ProposedCitation(index=idx, source_url=url, anchor=None))
    return answer_text, proposed


def _parse_text_response(
    answer_text: str, chunks: list[RetrievedChunk]
) -> list[ProposedCitation]:
    """Build the proposed-citations list from a plain-text answer.

    Each ``[N]`` marker in ``answer_text`` is resolved to a URL via
    either a trailing ``[N] <url>`` reference line (when present) or a
    positional match against ``chunks`` (the generation prompt numbers
    sources 1..N). Returns ``[]`` when no marker resolves to a URL.
    """

    from agents.state import ProposedCitation  # noqa: PLC0415

    # Collect inline markers in order of appearance, dedup preserving order.
    seen: set[int] = set()
    ordered_indices: list[int] = []
    for match in _CITE_MARKER_RE.finditer(answer_text):
        idx = int(match.group(1))
        if idx not in seen:
            seen.add(idx)
            ordered_indices.append(idx)

    if not ordered_indices:
        return []

    reference_map: dict[int, str] = {
        int(m.group(1)): m.group(2)
        for m in _REFERENCE_LINE_RE.finditer(answer_text)
    }

    proposed: list[ProposedCitation] = []
    for idx in ordered_indices:
        url: str | None = reference_map.get(idx)
        if url is None and 1 <= idx <= len(chunks):
            url = chunks[idx - 1]["source_url"]
        if url is None:
            continue
        proposed.append(ProposedCitation(index=idx, source_url=url, anchor=None))
    return proposed


def _parse_response(
    response: Any, chunks: list[RetrievedChunk]
) -> tuple[str, list[ProposedCitation]]:
    """Extract ``(answer_text, proposed_citations)`` from a Messages reply.

    Production posture: prefer the ``cite_answer`` ``tool_use`` block.
    Falls back to plain-text parsing (``[N]`` markers + a trailing
    ``[N] <url>`` reference table) so the conftest's text-mode mock keeps
    working through Slice 1. Returns ``("", [])`` when nothing useful
    can be extracted — caller treats that as a ``no-source`` refusal.
    """

    content_blocks: list[Any] = list(getattr(response, "content", []) or [])

    for block in content_blocks:
        if (
            getattr(block, "type", None) == "tool_use"
            and getattr(block, "name", None) == "cite_answer"
        ):
            return _parse_tool_use_block(block)

    text_parts: list[str] = [
        str(getattr(block, "text", ""))
        for block in content_blocks
        if getattr(block, "type", None) == "text"
    ]
    answer_text = "\n".join(text_parts).strip()
    if not answer_text:
        return "", []
    return answer_text, _parse_text_response(answer_text, chunks)


class GenerationNode:
    """LangGraph node implementing ``generation_node`` (T041).

    Satisfies :class:`agents.node_protocol.NodeProtocol`. Calls Claude
    Sonnet 4.6 via the Anthropic Messages API with a single ``cite_answer``
    tool that pins the response to a typed JSON payload. Records a
    ``node_invocation`` row on every call (Principle V).

    Parameters
    ----------
    client:
        Pre-configured :class:`anthropic.AsyncAnthropic`. Injected so
        tests can swap in a respx-mocked client without touching the
        production settings.
    session_factory:
        Async-session context-manager factory used to write the
        ``node_invocation`` row.
    processing_region:
        Opaque region label recorded on the audit row. Defaults are
        wired by the graph builder (T046) from
        :attr:`config.settings.Settings.anthropic_region`.
    model:
        Override the Anthropic model id. Defaults to
        :data:`MODEL_IDENTITY`.
    max_tokens:
        Generation cap. Defaults to :data:`DEFAULT_MAX_TOKENS`.
    """

    name: str = "generation_node"
    model_identity: str | None = MODEL_IDENTITY
    model_version: str | None = MODEL_VERSION

    def __init__(
        self,
        *,
        client: AsyncAnthropic,
        session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
        processing_region: str,
        model: str = MODEL_IDENTITY,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        if max_tokens <= 0:
            raise ValueError(f"max_tokens must be positive, got {max_tokens}")
        self._client = client
        self._session_factory = session_factory
        self._processing_region = processing_region
        self._model = model
        self._max_tokens = max_tokens

    async def __call__(self, state: ChatTurnState) -> ChatTurnState:
        """Generate the cited answer (or set a no-source refusal)."""

        from agents.state import RefusalState  # noqa: PLC0415

        query_id = state["query_id"]
        masked_query = state.get("masked_text") or state["original_text"]
        chunks = state.get("retrieved_chunks") or []

        # Defensive: with no chunks there is nothing to ground the answer
        # in, so short-circuit to a no-source refusal without burning a
        # model call.
        if not chunks:
            state["refusal"] = RefusalState(
                reason_code="no-source",
                user_message=(
                    "I couldn't find an ATO source covering this question."
                ),
                produced_by_node="generation_node",
            )
            return state

        user_message = _build_user_message(masked_query, chunks)

        # Cast the literal dicts to the SDK's typed param aliases so the
        # ``messages.create`` overload resolves to the non-streaming
        # ``Message`` return path.
        tool_param: ToolParam = cast("ToolParam", _CITE_ANSWER_TOOL_DICT)
        tool_choice_param: ToolChoiceToolParam = {
            "type": "tool",
            "name": "cite_answer",
        }

        started_at = datetime.now(tz=UTC)
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=SYSTEM_PROMPT,
            tools=[tool_param],
            tool_choice=tool_choice_param,
            messages=[{"role": "user", "content": user_message}],
        )
        finished_at = datetime.now(tz=UTC)

        # Anthropic's response carries the actual model identifier — fall
        # back to the constructor value if absent (e.g. partial mocks).
        response_model = getattr(response, "model", None) or self._model
        usage = getattr(response, "usage", None)
        input_tokens: int | None = (
            getattr(usage, "input_tokens", None) if usage is not None else None
        )
        output_tokens: int | None = (
            getattr(usage, "output_tokens", None) if usage is not None else None
        )

        async with self._session_factory() as session:
            audit_writer = AuditWriter(
                audit_record_repo=AuditRecordRepo(session),
                node_invocation_repo=NodeInvocationRepo(session),
            )
            await audit_writer.write_node_invocation(
                query_id,
                node_name=self.name,
                started_at=started_at,
                finished_at=finished_at,
                model_identity=response_model,
                model_version=self.model_version,
                processing_region=self._processing_region,
                input_token_count=input_tokens,
                output_token_count=output_tokens,
            )
            await session.commit()

        answer_text, proposed_citations = _parse_response(response, chunks)

        if not answer_text or not proposed_citations:
            state["refusal"] = RefusalState(
                reason_code="no-source",
                user_message=(
                    "I couldn't find an ATO source covering this question."
                ),
                produced_by_node="generation_node",
            )
            return state

        state["generated_text"] = answer_text
        state["proposed_citations"] = proposed_citations
        return state


__all__ = [
    "DEFAULT_MAX_TOKENS",
    "MODEL_IDENTITY",
    "MODEL_VERSION",
    "SYSTEM_PROMPT",
    "GenerationNode",
]
