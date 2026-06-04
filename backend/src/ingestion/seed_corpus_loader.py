"""Seed-corpus loader (T036).

Reads the hand-curated HTML pages under ``backend/data/seed_corpus/``
(captured under T037) and inserts ``source_document`` + ``chunk`` rows
for each entry. Used as the bootstrap path for User Story 1 (MVP)
before the real ingestion pipeline (US4 + US5) is online.

Design notes
============

* Each HTML file is paired with an entry in ``manifest.yaml`` that
  carries the canonical ATO ``source_url`` and basic provenance
  (``fetched_at``, ``http_status``, ``bytes``). The loader trusts the
  manifest for those fields; it does *not* reuse the manifest's
  ``content_hash_sha256`` — that hash is of the raw HTML bytes, but
  ``source_document.content_hash`` is defined in ``data-model.md`` as
  the SHA-256 of the *extracted main text*. The loader recomputes it
  after trafilatura extraction.
* Main-content extraction uses :func:`trafilatura.extract`. On the
  small handful of ATO pages where trafilatura returns an empty result
  the loader records an extraction warning and skips the entry rather
  than inserting an empty document; the alternative (the
  ``selectolax`` body-tag fallback in T105) is out of scope for this
  bootstrap-only path.
* Chunking is intentionally simple: paragraph splits, then a sliding
  token window of ~500 tokens with ~80 token overlap. The token
  approximation is the standard ``len(text) // 4`` heuristic; the real
  token-aware chunker (T106) is a US5 deliverable.
* Embeddings are produced in a single :meth:`VoyageEmbedder.embed_texts`
  call per source (the embedder batches internally per
  :data:`voyageai.VOYAGE_EMBED_BATCH_SIZE`).
* Idempotency: an entry whose ``source_url`` already has an active
  (non-superseded) :class:`SourceDocument` row is skipped. This lets
  the loader be re-run safely after partial failures without
  duplicating Voyage spend.

The module's ``__main__`` block constructs the embedder and session
factory from :mod:`config.settings` and runs the loader against
``backend/data/seed_corpus/``. **Running it consumes Voyage API
credits and is a manual operator action**, not part of any automated
test.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import trafilatura
import yaml

from db.repos.chunk import ChunkRepo
from db.repos.source_document import SourceDocumentRepo

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractAsyncContextManager

    from sqlalchemy.ext.asyncio import AsyncSession

    from .embedder.voyage_embedder import VoyageEmbedder


_LOG = logging.getLogger(__name__)

#: Token budget per chunk. Matches the US5 chunker's defaults.
_CHUNK_TOKENS: int = 500

#: Overlap budget between consecutive chunks (~80 tokens).
_CHUNK_OVERLAP_TOKENS: int = 80

#: Coarse chars-per-token heuristic. Voyage's tokenizer is not exposed
#: publicly; for a bootstrap loader on plain English HTML this is
#: accurate enough. Replaced by a real tokenizer in T106.
_CHARS_PER_TOKEN: int = 4

_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n+")


def _default_seed_corpus_dir() -> Path:
    """Return ``backend/data/seed_corpus`` resolved relative to this module.

    Kept as a sync helper because :meth:`Path.resolve` walks the
    filesystem (symlink resolution); calling it inside an async function
    trips ``ASYNC240``. Resolution happens once at CLI start, not in any
    test path.
    """

    return Path(__file__).resolve().parents[2] / "data" / "seed_corpus"


@dataclass(frozen=True)
class SeedLoadReport:
    """Outcome of a :func:`load_seed_corpus` invocation."""

    loaded: int = 0
    skipped: int = 0
    chunks_total: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)


def _parse_iso8601(value: str) -> datetime:
    """Parse a Z-suffixed ISO-8601 manifest timestamp into a UTC ``datetime``."""
    # ``fromisoformat`` accepts ``+00:00`` but not the bare ``Z`` suffix in
    # earlier Python 3.12 patches; normalize for robustness.
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    return datetime.fromisoformat(normalized)


def _approx_token_count(text: str) -> int:
    """Approximate token count via the ``len(text) // 4`` heuristic."""
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _chunk_text(
    main_text: str,
    *,
    chunk_tokens: int = _CHUNK_TOKENS,
    overlap_tokens: int = _CHUNK_OVERLAP_TOKENS,
) -> list[str]:
    """Split ``main_text`` into ~``chunk_tokens``-sized chunks with overlap.

    Algorithm: paragraph split first to keep semantic boundaries; pack
    paragraphs into the current chunk until the token budget is reached;
    on flush, carry the trailing ~``overlap_tokens`` tokens (measured as
    ~``overlap_tokens * 4`` characters) into the next chunk so retrieval
    boundary recall is not lost.
    """

    paragraphs = [p.strip() for p in _PARAGRAPH_SPLIT_RE.split(main_text) if p.strip()]
    if not paragraphs:
        return []

    target_chars = chunk_tokens * _CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * _CHARS_PER_TOKEN

    chunks: list[str] = []
    buffer: list[str] = []
    buffer_chars = 0
    for paragraph in paragraphs:
        para_chars = len(paragraph)
        if buffer and buffer_chars + para_chars > target_chars:
            chunks.append("\n\n".join(buffer))
            # Build the overlap tail: keep paragraphs from the end until
            # we have ~overlap_chars. Paragraph-aligned overlap preserves
            # sentence boundaries inside the carry.
            tail: list[str] = []
            tail_chars = 0
            for para in reversed(buffer):
                if tail_chars >= overlap_chars and tail:
                    break
                tail.insert(0, para)
                tail_chars += len(para)
            buffer = list(tail)
            buffer_chars = tail_chars
        buffer.append(paragraph)
        buffer_chars += para_chars

    if buffer:
        chunks.append("\n\n".join(buffer))
    return chunks


def _extract_main_text(html_path: Path) -> tuple[str | None, list[str]]:
    """Run trafilatura on ``html_path`` and return ``(main_text, warnings)``.

    Returns ``(None, [...])`` when extraction yields no content; the
    caller treats this as a soft failure and records the warnings on
    the :class:`SeedLoadReport`.
    """

    raw = html_path.read_text(encoding="utf-8", errors="replace")
    extracted = trafilatura.extract(
        raw,
        favor_recall=True,
        include_comments=False,
        include_tables=True,
        include_links=False,
    )
    if not extracted or not extracted.strip():
        return None, ["trafilatura returned empty main_text"]
    return extracted.strip(), []


async def _load_entry(
    entry: dict[str, Any],
    *,
    directory: Path,
    embedder: VoyageEmbedder,
    session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
) -> tuple[bool, int, dict[str, Any] | None]:
    """Load one manifest entry. Returns ``(loaded, chunks_inserted, error)``.

    ``loaded`` is ``False`` when the entry was a no-op skip (already
    present, idempotent re-run). ``error`` is a structured dict when
    the entry failed; both ``loaded`` and ``chunks_inserted`` are 0 in
    that case.
    """

    slug = str(entry.get("slug", "<unknown>"))
    source_url = str(entry["source_url"])
    html_path = directory / f"{slug}.html"

    if not html_path.exists():
        return False, 0, {"slug": slug, "error": f"missing html file: {html_path.name}"}

    main_text, warnings = _extract_main_text(html_path)
    if main_text is None:
        return False, 0, {"slug": slug, "error": "extraction failed", "warnings": warnings}

    chunks = _chunk_text(main_text)
    if not chunks:
        return False, 0, {"slug": slug, "error": "no chunks produced from main_text"}

    # Embed the chunks in one logical call; the embedder batches under
    # Voyage's per-request ceiling internally.
    embeddings = await embedder.embed_texts(chunks, input_type="document")
    if len(embeddings) != len(chunks):
        return (
            False,
            0,
            {
                "slug": slug,
                "error": (f"embedder returned {len(embeddings)} vectors for {len(chunks)} chunks"),
            },
        )

    content_hash = hashlib.sha256(main_text.encode("utf-8")).digest()
    fetched_at = _parse_iso8601(str(entry["fetched_at"]))
    http_status = int(entry.get("http_status", 200))

    async with session_factory() as session:
        source_repo = SourceDocumentRepo(session)
        chunk_repo = ChunkRepo(session)

        existing = await source_repo.find_active_by_url(source_url)
        if existing is not None:
            return False, 0, None  # idempotent skip

        doc = await source_repo.insert(
            source_url=source_url,
            fetched_at=fetched_at,
            content_hash=content_hash,
            main_text=main_text,
            http_status=http_status,
            source_last_modified=None,
            extraction_warnings=warnings,
        )

        for index, (chunk_text, vector) in enumerate(zip(chunks, embeddings, strict=True)):
            await chunk_repo.insert(
                source_document_id=doc.id,
                chunk_index=index,
                text_value=chunk_text,
                token_count=_approx_token_count(chunk_text),
                embedding=vector,
            )

        await session.commit()

    return True, len(chunks), None


async def load_seed_corpus(
    directory: Path,
    embedder: VoyageEmbedder,
    session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
) -> SeedLoadReport:
    """Load the seed corpus under ``directory`` into the DB.

    Reads ``directory / "manifest.yaml"`` and processes each entry.
    Already-present (active) source URLs are skipped. Failures are
    recorded on the report rather than aborting the run so a partial
    re-run can fix specific entries.
    """

    manifest_path = directory / "manifest.yaml"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest not found at {manifest_path}")

    with manifest_path.open("r", encoding="utf-8") as handle:
        manifest = yaml.safe_load(handle)

    entries = list(manifest.get("entries", []))
    if not entries:
        return SeedLoadReport()

    loaded = 0
    skipped = 0
    chunks_total = 0
    errors: list[dict[str, Any]] = []

    for entry in entries:
        try:
            was_loaded, n_chunks, error = await _load_entry(
                entry,
                directory=directory,
                embedder=embedder,
                session_factory=session_factory,
            )
        except Exception as exc:
            _LOG.exception("seed-corpus entry failed: %s", entry.get("slug"))
            errors.append({"slug": entry.get("slug"), "error": repr(exc)})
            continue

        if error is not None:
            errors.append(error)
            continue
        if was_loaded:
            loaded += 1
            chunks_total += n_chunks
        else:
            skipped += 1

    return SeedLoadReport(
        loaded=loaded,
        skipped=skipped,
        chunks_total=chunks_total,
        errors=errors,
    )


async def _cli() -> None:
    """CLI entry point: construct embedder + session factory from settings.

    Imports are deferred so ``python -c 'import seed_corpus_loader'``
    succeeds in environments without ``.env.local`` (the embedder and
    session factory both require API keys / DB URLs).
    """

    # Deferred imports — see docstring above. These all pull in env-var
    # validation or heavy SDK code; keeping them inside ``_cli`` means
    # ``python -m ingestion.seed_corpus_loader --help`` can short-circuit
    # without a live ``.env.local``.
    from config.settings import get_settings  # noqa: PLC0415
    from db.repos import get_sessionmaker  # noqa: PLC0415

    from .embedder.voyage_embedder import VoyageEmbedder  # noqa: PLC0415

    settings = get_settings()
    embedder = VoyageEmbedder(api_key=settings.voyage_api_key)
    sessionmaker = get_sessionmaker()
    directory = _default_seed_corpus_dir()

    report = await load_seed_corpus(
        directory=directory,
        embedder=embedder,
        session_factory=sessionmaker.begin,
    )
    _LOG.info(
        "seed-corpus load complete: loaded=%d skipped=%d chunks=%d errors=%d",
        report.loaded,
        report.skipped,
        report.chunks_total,
        len(report.errors),
    )
    for err in report.errors:
        _LOG.warning("seed-corpus error: %s", err)


if __name__ == "__main__":  # pragma: no cover — manual operator action
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(_cli())
