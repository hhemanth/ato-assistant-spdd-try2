"""Typed application settings loaded from environment / .env.local.

All runtime configuration is centralised here so that every other module
imports a single, validated :class:`Settings` instance via
:func:`get_settings`. The fields mirror ``backend/.env.example`` 1:1; any
new variable added to the env template MUST appear here with an explicit
type and (when applicable) a default.

Secrets are typed as ``SecretStr`` so they cannot be accidentally logged
or serialised by the FastAPI OpenAPI generator.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import PostgresDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-wide configuration loaded from the environment.

    Loading order (pydantic-settings v2 default precedence):

    1. Explicit constructor arguments (used in tests).
    2. Environment variables (case-insensitive match on the field name).
    3. Variables present in ``.env.local`` at the working directory.

    Unknown variables are rejected (``extra="forbid"``) so that typos in
    ``.env.local`` fail fast rather than silently being ignored.
    """

    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="forbid",
        case_sensitive=False,
    )

    # --- Supabase (Sydney ap-southeast-2) ---
    supabase_db_url: PostgresDsn
    supabase_service_role_key: SecretStr

    # --- Anthropic Claude (US-hosted direct API) ---
    anthropic_api_key: SecretStr
    # Opaque audit-only label recorded into ``audit_record.processing_region_llm``
    # (FR-018a). Anthropic's HTTP responses do not advertise a region; this
    # field exists solely so the audit row carries a stable, queryable string
    # rather than the :data:`audit.audit_writer.REGION_UNKNOWN` sentinel.
    anthropic_region: str = "us-east-1"

    # --- Voyage AI embeddings (US-hosted) ---
    voyage_api_key: SecretStr

    # --- LangSmith observability ---
    # Uses LangSmith's modern LANGSMITH_* env-var naming (the SDK
    # switched from LANGCHAIN_* in late 2024). `langsmith_endpoint` is
    # optional and accepts the regional endpoints; setting it to
    # https://apac.api.smith.langchain.com routes traces through the
    # APAC region, which is materially closer to AU users.
    langsmith_api_key: SecretStr
    langsmith_project: str = "ato-assistant-dev"
    langsmith_tracing: bool = True
    langsmith_endpoint: str | None = None

    # --- Frontend CORS origin (optional override of the dev default) ---
    frontend_origin: str | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached process-wide :class:`Settings` instance.

    The cache guarantees a single validation pass per process and a
    stable identity for downstream consumers (handy in tests that
    monkeypatch a field).
    """

    return Settings()
