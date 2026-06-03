"""FastAPI application skeleton.

This module assembles the FastAPI app used by Uvicorn. ``POST /chat``
is implemented in :mod:`api.chat_route` (T047); ``GET /system-info``
remains a placeholder until T048 lands.

The build is wrapped in :func:`build_app` so tests can construct an
isolated app instance without depending on import-time side effects.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from importlib.metadata import PackageNotFoundError, metadata, version
from typing import Literal

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from api.chat_route import chat_router
from config.settings import get_settings

# ---------------------------------------------------------------------------
# Package metadata
# ---------------------------------------------------------------------------

_PACKAGE_NAME = "ato-assistant-backend"


def _package_version() -> str:
    """Return the installed package version or a dev fallback."""

    try:
        return version(_PACKAGE_NAME)
    except PackageNotFoundError:  # pragma: no cover — dev-only fallback
        return "0.0.0+local"


def _package_description() -> str:
    """Pull the project description from package metadata when available."""

    try:
        return metadata(_PACKAGE_NAME).get("Summary", "ATO Assistant Backend API")
    except PackageNotFoundError:  # pragma: no cover — dev-only fallback
        return "ATO Assistant Backend API"


# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------

_LOG = logging.getLogger("ato_assistant.api")


def _configure_logging() -> None:
    """Configure stdout JSON-line logging once per process."""

    if _LOG.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    _LOG.addHandler(handler)
    _LOG.setLevel(logging.INFO)
    _LOG.propagate = False


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    """Emit one JSON log line per HTTP request.

    Request bodies are deliberately NOT logged — inbound text flows
    through the PII guard later in the pipeline and only the
    redacted/masked state is safe to observe.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        start = time.perf_counter()
        response: Response
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000.0
            _LOG.exception(
                json.dumps(
                    {
                        "event": "http_request_error",
                        "method": request.method,
                        "path": request.url.path,
                        "duration_ms": round(duration_ms, 2),
                    }
                )
            )
            raise

        duration_ms = (time.perf_counter() - start) * 1000.0
        _LOG.info(
            json.dumps(
                {
                    "event": "http_request",
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                }
            )
        )
        return response


# ---------------------------------------------------------------------------
# Pydantic models mirroring contracts/api-chat.openapi.yaml
# ---------------------------------------------------------------------------

# ChatRequest / Citation / AnswerResponse / RefusalResponse / ChatResponse
# live in :mod:`api.models` so :mod:`api.chat_route` can import them
# without a circular dependency back through this module. Keep
# SystemInfo + Error here for now — T048 lifts SystemInfo to api.models
# when GET /system-info ships.


class SystemInfo(BaseModel):
    """Transparency payload — surfaces model and index identities."""

    llm_identity: str
    llm_version: str
    llm_region: str
    embedding_identity: str
    embedding_version: str
    embedding_region: str
    observability_identity: str
    observability_region: str
    index_version: str
    index_refreshed_at: datetime
    corpus_scope: list[str]


class Error(BaseModel):
    """Standard error envelope used by all non-200 responses."""

    error_code: str
    message: str


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class VersionResponse(BaseModel):
    name: str
    version: str


# ---------------------------------------------------------------------------
# App builder
# ---------------------------------------------------------------------------


_NOT_IMPLEMENTED_PAYLOAD: dict[str, str] = {
    "error_code": "not_implemented_yet",
    "message": "Routed in Phase 3 (US1) / Phase 2 finalize (T048).",
}


def build_app() -> FastAPI:
    """Build and return a configured :class:`FastAPI` instance.

    Wrapping construction in a function keeps the module side-effect-free
    enough to be imported by tests and by ad-hoc tools without booting
    a server.
    """

    _configure_logging()

    app = FastAPI(
        title="ATO Assistant Backend API",
        version=_package_version(),
        description=_package_description(),
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # --- CORS ---
    # Local Next.js dev + an optional configured origin (e.g. preview/prod).
    # Settings are loaded lazily here so importing this module never
    # requires every env var to be present (tests / `--version` need it).
    allowed_origins: list[str] = ["http://localhost:3000"]
    try:
        configured = get_settings().frontend_origin
        if configured and configured not in allowed_origins:
            allowed_origins.append(configured)
    except Exception as exc:  # boot must not require full env
        _LOG.warning(
            json.dumps(
                {
                    "event": "settings_unavailable_for_cors",
                    "fallback_origins": allowed_origins,
                    "error": str(exc),
                }
            )
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    app.add_middleware(StructuredLoggingMiddleware)

    # --- Health and version (live now) ---
    @app.get("/healthz", response_model=HealthResponse, tags=["meta"])
    async def healthz() -> HealthResponse:
        return HealthResponse()

    @app.get("/version", response_model=VersionResponse, tags=["meta"])
    async def version_endpoint() -> VersionResponse:
        return VersionResponse(name=_PACKAGE_NAME, version=_package_version())

    # --- POST /chat (T047) ---
    app.include_router(chat_router)

    # --- Contract placeholder (T048) ---
    @app.get(
        "/system-info",
        operation_id="getSystemInfo",
        tags=["meta"],
        summary="Transparency endpoint - model and index versions.",
        responses={
            200: {"model": SystemInfo},
            501: {"model": Error, "description": "Placeholder until T048 lands."},
        },
    )
    async def get_system_info() -> Response:
        # TODO(T048): return real model + index metadata.
        return JSONResponse(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            content=_NOT_IMPLEMENTED_PAYLOAD,
        )

    return app


app = build_app()
