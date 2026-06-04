"""Shared pytest fixtures for the ATO Assistant backend test suite.

Why this file looks the way it does:

* The backend uses a ``src/`` layout but ``pyproject.toml`` does not set a
  ``pythonpath`` (and is out of test-author write scope), so we inject
  ``backend/src`` onto ``sys.path`` **before** any of the test files
  attempt their ``from api.main import app`` style imports.
* ``pydantic-settings`` validates required env vars at construction.
  When the live ``.env.local`` is missing or incomplete, every DB
  fixture must skip cleanly rather than blow up at collection time.
* ``pytest-asyncio>=1.4`` no longer ships the legacy session-scoped
  ``event_loop`` fixture pattern. Tests use the per-test
  ``@pytest.mark.asyncio`` decorator and each gets its own loop —
  the dispatch's intent ("session-scoped loop") is incompatible with the
  installed framework version and would silently double-fixture.
* The Anthropic + Voyage mocks are scoped per test and use the exact
  upstream hostnames the SDKs hit by default (so respx actually
  intercepts the call).
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator, Iterator
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

# ---------------------------------------------------------------------------
# sys.path hack — MUST run before any `from api.*` / `from db.*` imports.
# ---------------------------------------------------------------------------

_BACKEND_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(_BACKEND_SRC))

import pytest
import pytest_asyncio


# ---------------------------------------------------------------------------
# Settings + DB fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def settings() -> "object":
    """Load process-wide :class:`Settings`; skip if env is incomplete."""

    try:
        from config.settings import get_settings  # type: ignore[import-not-found]

        return get_settings()
    except Exception as exc:  # ValidationError, missing key, etc.
        pytest.skip(f"backend settings unavailable (live env missing): {exc}")


@pytest.fixture()
def async_db_url(settings: "object") -> str:
    """Return the supabase DB URL rewritten to use the psycopg3 async driver."""

    raw = str(settings.supabase_db_url)  # type: ignore[attr-defined]
    # PostgresDsn produces ``postgresql://...``; SQLAlchemy async needs the
    # explicit psycopg dialect prefix.
    if raw.startswith("postgresql+psycopg://"):
        return raw
    if raw.startswith("postgresql://"):
        return "postgresql+psycopg://" + raw[len("postgresql://") :]
    if raw.startswith("postgres://"):
        return "postgresql+psycopg://" + raw[len("postgres://") :]
    return raw


@pytest_asyncio.fixture()
async def engine(async_db_url: str) -> "AsyncIterator[object]":
    """Create a transient async engine bound to the live Supabase DB.

    Every test that depends on this fixture is auto-skipped if the live
    DB is unreachable so the suite can run on machines without DB
    credentials.
    """

    try:
        from sqlalchemy.ext.asyncio import create_async_engine
    except Exception as exc:  # pragma: no cover — sqlalchemy is a hard dep
        pytest.skip(f"SQLAlchemy not installed: {exc}")

    try:
        eng = create_async_engine(async_db_url, future=True, pool_pre_ping=True)
    except Exception as exc:
        pytest.skip(f"async engine could not be created (missing driver?): {exc}")

    # Probe the connection so we can skip fast when the live DB is down
    # OR when the async runtime (greenlet, psycopg async) isn't installed.
    try:
        from sqlalchemy import text

        async with eng.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        try:
            await eng.dispose()
        except Exception:  # secondary failure during teardown
            pass
        pytest.skip(f"live Supabase DB not reachable: {exc}")
    try:
        yield eng
    finally:
        try:
            await eng.dispose()
        except Exception:
            pass


@pytest_asyncio.fixture()
async def db_session(engine: "object") -> "AsyncIterator[object]":
    """Yield a transactional async session that rolls back on exit.

    Pattern: open a connection, begin an outer transaction, bind a
    session to it, and roll back the transaction at the end. The live
    DB is therefore never mutated by the test suite (FR-018a residency
    aside — we just don't write).
    """

    from sqlalchemy.exc import ProgrammingError
    from sqlalchemy.ext.asyncio import AsyncSession

    async with engine.begin() as conn:  # type: ignore[attr-defined]
        # Probe for the schema; skip cleanly if the migration isn't applied.
        try:
            from sqlalchemy import text

            await conn.execute(text("SELECT 1 FROM source_document LIMIT 1"))
        except ProgrammingError as exc:
            pytest.skip(f"DB schema not applied (run 0001_initial_schema.sql): {exc}")

        # ``join_transaction_mode="create_savepoint"`` makes
        # ``session.commit()`` calls in production code (now required so
        # graph nodes actually persist) release a SAVEPOINT rather than
        # ending the outer transaction. The outer ``conn.rollback()`` at
        # the end of the test still undoes everything the test wrote.
        session = AsyncSession(
            bind=conn,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            await conn.rollback()


# ---------------------------------------------------------------------------
# HTTP mocks for Anthropic + Voyage
# ---------------------------------------------------------------------------

_FAKE_ATO_URL = "https://www.ato.gov.au/individuals/income-and-deductions/tax-free-threshold"
_FAKE_ANSWER_TEXT = (
    "The tax-free threshold in Australia is $18,200 for the financial year. "
    "Income earned below this threshold is not subject to income tax [1].\n"
    f"\n[1] {_FAKE_ATO_URL}"
)


@pytest.fixture()
def mocked_anthropic() -> Iterator["object"]:
    """Stub the Anthropic Messages API with a deterministic reply.

    The reply body contains exactly one ``[1]`` marker and a matching
    reference line so the citation-alignment check has something to
    verify against the seeded chunk.
    """

    try:
        import respx
        from httpx import Response
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"respx not installed: {exc}")

    with respx.mock(assert_all_called=False) as mock:
        mock.post("https://api.anthropic.com/v1/messages").mock(
            return_value=Response(
                200,
                json={
                    "id": "msg_test_001",
                    "type": "message",
                    "role": "assistant",
                    "model": "claude-sonnet-4-6",
                    "content": [{"type": "text", "text": _FAKE_ANSWER_TEXT}],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 64, "output_tokens": 96},
                },
            )
        )
        yield mock


@pytest.fixture()
def voyage_embedding() -> list[float]:
    """Deterministic 1024-dim Voyage embedding (a single non-zero index).

    Concentrating mass on one index keeps cosine similarity easy to
    reason about for the seeded chunk.
    """

    vec = [0.0] * 1024
    vec[7] = 1.0
    return vec


@pytest.fixture()
def mocked_voyage(voyage_embedding: list[float]) -> Iterator["object"]:
    """Stub the Voyage embeddings endpoint with a deterministic vector."""

    try:
        import respx
        from httpx import Response
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"respx not installed: {exc}")

    with respx.mock(assert_all_called=False) as mock:
        mock.post("https://api.voyageai.com/v1/embeddings").mock(
            return_value=Response(
                200,
                json={
                    "object": "list",
                    "data": [{"object": "embedding", "embedding": voyage_embedding, "index": 0}],
                    "model": "voyage-3-large",
                    "usage": {"total_tokens": 8},
                },
            )
        )
        yield mock


# ---------------------------------------------------------------------------
# Seeded corpus fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def seeded_chunks(
    db_session: "object", voyage_embedding: list[float]
) -> "AsyncIterator[dict[str, object]]":
    """Insert one source_document + one chunk wired to the deterministic vector.

    Rolled back by ``db_session``'s outer transaction. Returns the inserted
    IDs + source URL so tests can assert linkage downstream.
    """

    from db.repos.chunk import ChunkRepo  # type: ignore[import-not-found]
    from db.repos.source_document import (  # type: ignore[import-not-found]
        SourceDocumentRepo,
    )

    source_repo = SourceDocumentRepo(db_session)  # type: ignore[arg-type]
    chunk_repo = ChunkRepo(db_session)  # type: ignore[arg-type]

    fetched_at = datetime.now(tz=timezone.utc)
    doc = await source_repo.insert(
        source_url=_FAKE_ATO_URL,
        fetched_at=fetched_at,
        content_hash=b"\x00" * 32,
        main_text=(
            "The tax-free threshold in Australia is $18,200. "
            "Income earned below this threshold is not subject to income tax."
        ),
        http_status=200,
        source_last_modified=fetched_at,
    )
    chunk = await chunk_repo.insert(
        source_document_id=doc.id,
        chunk_index=0,
        text_value=(
            "The tax-free threshold in Australia is $18,200. "
            "Income earned below this threshold is not subject to income tax."
        ),
        token_count=24,
        embedding=voyage_embedding,
    )

    yield {
        "source_document_id": doc.id,
        "chunk_id": chunk.id,
        "source_url": _FAKE_ATO_URL,
        "session_id": uuid4(),
    }


# ---------------------------------------------------------------------------
# Graph fixture: builds the real LangGraph against the mocked HTTP layer +
# the test's transactional session, and registers it with the chat route's
# injection seam (``set_graph_for_tests``). Tests that depend on this
# fixture exercise the full LangGraph topology end-to-end while every
# external call is intercepted by respx and every DB write lives inside
# the outer transactional rollback.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def test_graph(
    db_session: "object",
    mocked_anthropic: "object",
    voyage_embedding: list[float],
) -> "AsyncIterator[object]":
    """Build a LangGraph wired to a stub embedder + mocked Anthropic + the
    test's transactional session.

    Notes:

    * The Anthropic SDK uses httpx, so the ``mocked_anthropic`` respx
      fixture intercepts its HTTP calls cleanly.
    * The ``voyageai`` SDK does NOT use httpx (it uses its own internal
      HTTP layer that respx can't see), so we replace the embedder
      itself with a tiny stub that returns the deterministic vector.
      The ``VoyageEmbedder`` class is exercised separately by unit
      tests; here we only need the embeddings the retrieval node
      depends on.
    * All graph nodes that ``async with self.session_factory() as session:``
      receive the same ``db_session`` instance via a thin
      context-manager wrapper, so every write the graph performs
      lives inside the outer rollback.

    Yields the compiled graph and clears the test-injection seam on
    teardown.
    """

    from contextlib import asynccontextmanager

    from agents.graph import GraphDeps, build_graph  # type: ignore[import-not-found]
    from agents.retrieval.pgvector_client import (  # type: ignore[import-not-found]
        PgVectorClient,
    )
    from anthropic import AsyncAnthropic
    from api.chat_route import set_graph_for_tests  # type: ignore[import-not-found]

    @asynccontextmanager
    async def _session_cm() -> "AsyncIterator[object]":
        """Yield the test's transactional session without closing it."""

        yield db_session

    def session_factory() -> "object":
        return _session_cm()

    class _StubEmbedder:
        """Tiny VoyageEmbedder stand-in: always returns the seeded vector."""

        model: str = "voyage-3-large"
        output_dimension: int = 1024

        def __init__(self, vec: list[float]) -> None:
            self._vec = vec

        async def embed_query(self, text: str) -> list[float]:
            return list(self._vec)

        async def embed_document(self, text: str) -> list[float]:
            return list(self._vec)

        async def embed_texts(
            self,
            texts: list[str],
            input_type: str = "document",
        ) -> list[list[float]]:
            return [list(self._vec) for _ in texts]

    embedder = _StubEmbedder(voyage_embedding)
    retrieval_client = PgVectorClient(session_factory=session_factory)  # type: ignore[arg-type]
    anthropic_client = AsyncAnthropic(api_key="test")

    deps = GraphDeps(
        session_factory=session_factory,  # type: ignore[arg-type]
        embedder=embedder,
        retrieval_client=retrieval_client,
        anthropic_client=anthropic_client,
        processing_region_llm="us-east-1",
        processing_region_embedding="unknown",
        processing_region_observability="apac",
    )
    graph = build_graph(deps)
    set_graph_for_tests(graph)
    try:
        yield graph
    finally:
        set_graph_for_tests(None)
