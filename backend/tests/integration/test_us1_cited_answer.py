"""T028 [US1] Integration test — cited-answer flow over the seed corpus.

End-to-end happy path through the LangGraph: a seeded ``source_document``
+ ``chunk`` is found by the retrieval node, the mocked Voyage embedder
produces the deterministic query vector, the mocked Anthropic API returns
a citation-bearing text, and the finalize node writes ``answer`` +
``citation`` + ``audit_record`` rows.

Expected failure today: the placeholder ``POST /chat`` route returns
``501 Not Implemented`` — the test asserts the status code BEFORE
requesting the DB-dependent fixtures so the failure tail is the clean
``501 != 200`` TDD signal even on machines where the live DB driver
(greenlet / psycopg async) isn't installed.

Post-T047 (the real LangGraph route), the lazy ``request.getfixturevalue``
calls pull in ``seeded_chunks`` + ``db_session`` and verify the DB
linkage (audit_record → answer → citation row carrying the seeded ATO
URL).
"""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from api.main import app  # type: ignore[import-not-found]
from disclaimers.templates import PER_ANSWER  # type: ignore[import-not-found]


@pytest.mark.asyncio
async def test_cited_answer_flow_writes_audit_and_citation(
    test_graph: object,
    seeded_chunks: dict[str, object],
    db_session: object,
) -> None:
    """Drive a full chat turn end-to-end and assert audit + citation linkage.

    ``test_graph`` (conftest) builds the real LangGraph against mocked
    Voyage + Anthropic HTTP layers and registers it with the chat route's
    injection seam. ``seeded_chunks`` must be requested EAGERLY so the
    chunk lands in the DB before the POST kicks off retrieval (lazy
    ``request.getfixturevalue`` would seed only after the POST returned
    a no-source refusal).
    """

    session_id = uuid.uuid4()
    payload = {
        "text": "What is the tax-free threshold in Australia?",
        "session_id": str(session_id),
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/chat", json=payload)

    assert response.status_code == 200, (
        f"POST /chat must reach the real LangGraph; got {response.status_code}: {response.text}"
    )

    body = response.json()
    assert body["kind"] == "answer", body
    query_id = uuid.UUID(body["query_id"])

    # The per-answer disclaimer (FR-003) MUST be present.
    assert PER_ANSWER in body["per_answer_disclaimer"], body["per_answer_disclaimer"]

    seeded_url = str(seeded_chunks["source_url"])

    # audit_record row was written for this query_id.
    audit_row = (
        await db_session.execute(
            text("SELECT id, answer_id, refusal_id FROM audit_record WHERE query_id = :qid"),
            {"qid": str(query_id)},
        )
    ).one_or_none()
    assert audit_row is not None, "audit_record row was not written for the query"
    assert audit_row.answer_id is not None, "audit_record must link to an answer row"
    assert audit_row.refusal_id is None, "successful turn must not link to a refusal"

    # answer row exists and matches.
    answer_row = (
        await db_session.execute(
            text("SELECT id FROM answer WHERE query_id = :qid"),
            {"qid": str(query_id)},
        )
    ).one_or_none()
    assert answer_row is not None, "answer row missing"
    assert answer_row.id == audit_row.answer_id

    # At least one citation row exists with the seeded ATO URL.
    cite_rows = (
        await db_session.execute(
            text("SELECT source_url FROM citation WHERE answer_id = :aid"),
            {"aid": str(answer_row.id)},
        )
    ).all()
    assert cite_rows, "no citation rows attached to the answer"
    cited_urls = {row.source_url for row in cite_rows}
    assert seeded_url in cited_urls, (
        f"expected seeded ATO URL {seeded_url!r} among citations {cited_urls!r}"
    )
