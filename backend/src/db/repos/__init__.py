"""Typed repository modules for every ATO Assistant entity (T014).

Each entity gets its own file under :mod:`db.repos`. Modules expose a
SQLAlchemy 2.x typed declarative model (subclass of :class:`Base`) and a
repository class (subclass of :class:`RepoBase`) carrying the
entity-specific lookups required by the spec's functional requirements.

The package also provides a lazy async-engine + session factory so test
code can construct repositories with a mock session without triggering
environment-variable loading at import time. The factory defers the
``config.settings`` import until called so unit tests that never touch
the DB never need real env vars.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .answer import Answer, AnswerRepo
from .audit_record import AuditRecord, AuditRecordRepo
from .base import Base, RepoBase
from .chunk import Chunk, ChunkRepo
from .citation import Citation, CitationRepo
from .crawl_run import CrawlRun, CrawlRunRepo
from .eval_question import EvalQuestion, EvalQuestionRepo
from .eval_result import EvalResult, EvalResultRepo
from .eval_run import EvalRun, EvalRunRepo
from .node_invocation import NodeInvocation, NodeInvocationRepo
from .query import Query, QueryRepo
from .refusal import Refusal, RefusalRepo
from .retrieval import Retrieval, RetrievalRepo
from .source_document import SourceDocument, SourceDocumentRepo
from .url_inventory import UrlInventory, UrlInventoryRepo

__all__ = [
    "Answer",
    "AnswerRepo",
    "AuditRecord",
    "AuditRecordRepo",
    "Base",
    "Chunk",
    "ChunkRepo",
    "Citation",
    "CitationRepo",
    "CrawlRun",
    "CrawlRunRepo",
    "EvalQuestion",
    "EvalQuestionRepo",
    "EvalResult",
    "EvalResultRepo",
    "EvalRun",
    "EvalRunRepo",
    "NodeInvocation",
    "NodeInvocationRepo",
    "Query",
    "QueryRepo",
    "Refusal",
    "RefusalRepo",
    "RepoBase",
    "Retrieval",
    "RetrievalRepo",
    "SourceDocument",
    "SourceDocumentRepo",
    "UrlInventory",
    "UrlInventoryRepo",
    "get_engine",
    "get_sessionmaker",
]


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Return a cached async SQLAlchemy engine built from settings.

    The ``config.settings`` import is intentionally deferred to the call
    site so importing :mod:`db.repos` does not require the runtime env
    vars (useful for unit tests that mock the session).
    """
    from config.settings import get_settings

    settings = get_settings()
    return create_async_engine(str(settings.supabase_db_url), future=True)


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return a cached async session factory bound to :func:`get_engine`."""
    return async_sessionmaker(get_engine(), expire_on_commit=False)
