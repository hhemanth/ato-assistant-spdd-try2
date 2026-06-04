"""Pydantic request/response models for the FastAPI HTTP surface.

Lifted from :mod:`api.main` so :mod:`api.chat_route` and any future
endpoint module can import them without a circular dependency through
:mod:`api.main` (which builds the FastAPI app and registers routers).

NOTE: These models mirror ``specs/001-ato-chat-rag/contracts/api-chat.openapi.yaml``.
Keep them in sync — the OpenAPI drift check (T141) compares the live
FastAPI schema against the YAML contract.

``SystemInfo`` + ``Error`` deliberately stay in :mod:`api.main` for
now; T048 (Slice 3) lifts ``SystemInfo`` here when ``GET /system-info``
is implemented.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    """User-submitted question. Validated before any LLM is reached."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="User's question. Server runs the PII guard before any LLM call.",
    )
    session_id: UUID = Field(
        ...,
        description="Client-generated stable id for the browser session.",
    )


class Citation(BaseModel):
    """A single citation rendered alongside an answer."""

    index: int = Field(..., ge=1, description="Matches the [N] marker in `text`.")
    source_url: str = Field(
        ...,
        pattern=r"^https://www\.ato\.gov\.au/",
        description="MUST be an ato.gov.au URL.",
    )
    anchor: str | None = None
    snippet: str
    source_last_modified: datetime | None = None
    liveness_status: Literal["live", "unknown", "stale"]


class AnswerResponse(BaseModel):
    """A grounded answer with citations and confidence badge."""

    kind: Literal["answer"] = "answer"
    query_id: UUID
    text: str = Field(
        ...,
        description="Rendered answer. Contains inline citation markers like [1], [2].",
    )
    citations: list[Citation] = Field(..., min_length=1)
    confidence_band: Literal["high", "medium", "low"]
    per_answer_disclaimer: str
    model_identity: str = Field(..., description="e.g., claude-sonnet-4-6.")
    generated_at: datetime


class RefusalResponse(BaseModel):
    """A typed refusal payload — never an HTTP error."""

    kind: Literal["refusal"] = "refusal"
    query_id: UUID
    reason_code: Literal[
        "no-source",
        "low-confidence",
        "citation-misalignment",
        "stale-source",
        "pii-integral",
        "pii-scanner-fail",
        "out-of-scope",
        "inappropriate",
        "personal-advice",
        "non-english",
    ]
    user_message: str
    refused_at: datetime


ChatResponse = Annotated[
    AnswerResponse | RefusalResponse,
    Field(discriminator="kind"),
]


__all__ = [
    "AnswerResponse",
    "ChatRequest",
    "ChatResponse",
    "Citation",
    "RefusalResponse",
]
