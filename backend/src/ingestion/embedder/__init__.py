"""Embedding subpackage — Voyage AI wrappers used by ingestion + retrieval.

Only :class:`VoyageEmbedder` from :mod:`ingestion.embedder.voyage_embedder`
imports :mod:`voyageai` directly. Every other module in the codebase
goes through this facade so the SDK surface remains a single seam to
mock in tests (FR-018a transparency: every model call is logged via the
caller's ``node_invocation`` writer; the embedder itself is
deterministic — no model-state of its own).
"""

from .voyage_embedder import VoyageEmbedder

__all__ = ["VoyageEmbedder"]
