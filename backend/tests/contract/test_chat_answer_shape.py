"""T025 [US1] Contract test for ``POST /chat`` answer shape.

This test asserts that — once T047 lands the real LangGraph route —
``POST /chat`` returns a 200 ``AnswerResponse`` whose body matches the
``AnswerResponse`` schema in ``specs/001-ato-chat-rag/contracts/api-chat.openapi.yaml``.

While the placeholder is in place (the route returns 501), the FIRST
assertion (status code) fails cleanly — surfacing the right TDD-gate
signal rather than a confusing downstream KeyError.
"""

from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app  # type: ignore[import-not-found]

# Compile once — the contract is explicit: every citation source_url MUST
# match this regex (see api-chat.openapi.yaml::Citation::source_url::pattern).
_ATO_URL = re.compile(r"^https://www\.ato\.gov\.au/")
_ALLOWED_CONFIDENCE_BANDS = {"high", "medium", "low"}
_ALLOWED_LIVENESS = {"live", "unknown", "stale"}


@pytest.mark.asyncio
async def test_post_chat_returns_answer_response_matching_contract() -> None:
    """Post a simple chat request, verify the AnswerResponse contract.

    Required failure today: the placeholder route returns
    ``501 Not Implemented`` so the first assertion fails. The remaining
    assertions document the post-implementation contract surface.
    """

    payload = {
        "text": "What is the tax-free threshold in Australia?",
        "session_id": str(uuid4()),
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/chat", json=payload)

    # First gate — the placeholder returns 501; the eventual contract is 200.
    assert response.status_code == 200, (
        f"POST /chat must return 200 AnswerResponse, got "
        f"{response.status_code}: {response.text}"
    )

    body = response.json()

    # Discriminator + required top-level fields.
    assert body["kind"] == "answer", body
    UUID(body["query_id"])  # query_id MUST parse as a UUID per the contract
    assert isinstance(body["text"], str) and body["text"].strip(), body

    # Confidence band, disclaimer, model identity, generated_at.
    assert body["confidence_band"] in _ALLOWED_CONFIDENCE_BANDS, body
    assert isinstance(body["per_answer_disclaimer"], str)
    assert body["per_answer_disclaimer"].strip(), body
    assert isinstance(body["model_identity"], str) and body["model_identity"].strip(), body
    # generated_at MUST parse as ISO 8601.
    datetime.fromisoformat(body["generated_at"].replace("Z", "+00:00"))

    # Citations array — at least one, every entry conforms to Citation.
    citations = body["citations"]
    assert isinstance(citations, list) and len(citations) >= 1, body
    for c in citations:
        assert isinstance(c["index"], int) and c["index"] >= 1, c
        assert isinstance(c["source_url"], str), c
        assert _ATO_URL.match(c["source_url"]), c["source_url"]
        assert isinstance(c["snippet"], str) and c["snippet"].strip(), c
        assert c["liveness_status"] in _ALLOWED_LIVENESS, c
        # Optional fields — must be the right shape when present.
        if c.get("anchor") is not None:
            assert isinstance(c["anchor"], str), c
        if c.get("source_last_modified") is not None:
            datetime.fromisoformat(c["source_last_modified"].replace("Z", "+00:00"))
