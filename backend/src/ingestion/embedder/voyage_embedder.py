"""Voyage AI embedder (T038).

A thin async facade over :class:`voyageai.AsyncClient` that batches
inputs at Voyage's documented batch size and returns plain
``list[list[float]]`` vectors at the dimension verified in T010
(``1024`` for ``voyage-3-large``).

Design notes
============

* This module is the ONLY place in the codebase that imports
  :mod:`voyageai`. Every other caller (ingestion, retrieval) imports
  :class:`VoyageEmbedder` and uses its typed methods so the SDK
  surface is a single seam for tests to mock.
* The embedder is *not* a LangGraph node — it carries no
  ``NodeProtocol`` attributes. It is invoked from inside the
  retrieval node and the ingestion pipeline; those callers own the
  ``node_invocation`` audit-row write per Principle V.
* Batching: Voyage's Python SDK exposes the per-request batch ceiling
  as :data:`voyageai.VOYAGE_EMBED_BATCH_SIZE` (128 at the time of
  T038). We slice ``texts`` into chunks of that size and concatenate
  the resulting embedding lists in order.
* ``output_dimension`` is forwarded to :meth:`voyageai.AsyncClient.embed`
  so the contract is explicit at the call site instead of relying on
  the model's default. The default :data:`VOYAGE_LARGE_DIM` matches
  the ``VECTOR(1024)`` column type in
  ``backend/src/db/migrations/0001_initial_schema.sql``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import SecretStr

if TYPE_CHECKING:
    from voyageai import AsyncClient as _VoyageAsyncClient

    # PEP 695 type alias (Python 3.12) — kept inside the ``TYPE_CHECKING``
    # block so the heavy ``voyageai`` import is type-only.
    type VoyageAsyncClient = _VoyageAsyncClient

#: Voyage ``voyage-3-large`` default embedding dimension (verified in T010).
VOYAGE_LARGE_DIM: int = 1024

#: Voyage's documented per-request batch ceiling. Sourced from the SDK
#: constant so a future SDK bump propagates automatically.
_DEFAULT_BATCH_SIZE: int = 128

InputType = Literal["document", "query"]


class VoyageEmbedder:
    """Async Voyage AI embedder used by ingestion + retrieval.

    Parameters
    ----------
    api_key:
        Voyage API key. Wrapped in :class:`pydantic.SecretStr` so it
        cannot be accidentally logged.
    model:
        Voyage model identifier. Defaults to ``voyage-3-large``.
    output_dimension:
        Embedding dimension to request from Voyage. Defaults to
        :data:`VOYAGE_LARGE_DIM` (= 1024) — the value baked into the
        ``chunk.embedding VECTOR(1024)`` column.
    client:
        Pre-built :class:`voyageai.AsyncClient` for tests. When
        ``None`` (production path) a fresh client is constructed with
        the supplied ``api_key``.
    batch_size:
        Per-request input ceiling. Defaults to
        :data:`voyageai.VOYAGE_EMBED_BATCH_SIZE` (128).
    """

    def __init__(
        self,
        *,
        api_key: SecretStr,
        model: str = "voyage-3-large",
        output_dimension: int = VOYAGE_LARGE_DIM,
        client: VoyageAsyncClient | None = None,
        batch_size: int = _DEFAULT_BATCH_SIZE,
    ) -> None:
        if batch_size <= 0:
            raise ValueError(f"batch_size must be positive, got {batch_size}")
        self._api_key = api_key
        self._model = model
        self._output_dimension = output_dimension
        self._batch_size = batch_size
        self._client: VoyageAsyncClient | None = client

    @property
    def model(self) -> str:
        """Provider model identifier (e.g. ``voyage-3-large``)."""
        return self._model

    @property
    def output_dimension(self) -> int:
        """Embedding dimension requested from Voyage."""
        return self._output_dimension

    def _get_client(self) -> VoyageAsyncClient:
        """Lazily construct the underlying SDK client.

        Deferred so module import does not require a live API key — the
        retrieval node and the ingestion pipeline both reach for the
        client only when an actual embed call is about to be made.
        """

        if self._client is None:
            # Local import: keeps the heavy ``voyageai`` import (which
            # pulls aiohttp and tenacity) out of the module-level import
            # graph so unit tests that mock the embedder don't pay for it.
            import voyageai  # noqa: PLC0415

            self._client = voyageai.AsyncClient(api_key=self._api_key.get_secret_value())
        return self._client

    async def embed_texts(
        self,
        texts: list[str],
        *,
        input_type: InputType = "document",
    ) -> list[list[float]]:
        """Embed ``texts`` in batches and return one vector per input.

        Voyage's per-request input cap is enforced by slicing
        ``texts`` into windows of ``self._batch_size``. Returned vectors
        preserve input order across batch boundaries.

        Empty input returns an empty list without making a network call.
        """

        if not texts:
            return []

        client = self._get_client()
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            result = await client.embed(
                texts=batch,
                model=self._model,
                input_type=input_type,
                output_dimension=self._output_dimension,
            )
            # ``EmbeddingsObject.embeddings`` is typed as
            # ``list[list[float]] | list[list[int]]`` because Voyage can
            # return packed ints when ``output_dtype`` is set. We never
            # set ``output_dtype``, so the default is float — narrow the
            # type explicitly for downstream callers.
            for vec in result.embeddings:
                vectors.append([float(component) for component in vec])
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string with ``input_type="query"``."""
        vectors = await self.embed_texts([text], input_type="query")
        return vectors[0]

    async def embed_document(self, text: str) -> list[float]:
        """Embed a single document string with ``input_type="document"``."""
        vectors = await self.embed_texts([text], input_type="document")
        return vectors[0]
