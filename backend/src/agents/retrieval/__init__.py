"""Retrieval subpackage — top-k pgvector lookup + LangGraph retrieval node.

The pgvector client (T039) is a thin facade over
:class:`db.repos.chunk.ChunkRepo` that emits the
:class:`agents.state.RetrievedChunk` value object the rest of the
LangGraph speaks.
"""

from .pgvector_client import PgVectorClient

__all__ = ["PgVectorClient"]
