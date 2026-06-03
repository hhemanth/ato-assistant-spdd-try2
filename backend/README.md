# ATO Assistant — Backend

Python 3.12 · FastAPI · LangGraph · Anthropic Claude · Voyage AI ·
Supabase Postgres + pgvector. Managed with **UV** (Astral).

The authoritative spec, plan, and tasks live under
[`../specs/001-ato-chat-rag/`](../specs/001-ato-chat-rag/).

## Local development

```bash
uv python install 3.12
uv sync --all-groups            # creates .venv, installs runtime + dev
cp .env.example .env.local      # then fill in real values — see below
```

Run the dev server:

```bash
uv run uvicorn src.api.main:app --reload --port 8000
```

Run lints + tests:

```bash
uv run ruff check src/
uv run mypy src/
uv run pytest                   # once Phase 3 lands the first tests
```

## Connecting to Supabase

The project's database lives in a Supabase project provisioned in the
**Sydney `ap-southeast-2`** region.

1. Open the Supabase Dashboard → your project → **Connect** (top-right)
   or **Project Settings → Database → Connection string**.
2. Pick the **Session pooler** tab. It's IPv4-compatible (Direct
   connection is IPv6-only and can bite you on macOS) and is fine for
   FastAPI's persistent connections.
3. Copy the **URI** form. It looks like:
   ```
   postgresql://postgres.<project-ref>:<password>@aws-0-ap-southeast-2.pooler.supabase.com:5432/postgres
   ```
4. **Prefix the scheme with `+psycopg`** so SQLAlchemy picks the
   psycopg3 driver:
   ```
   postgresql+psycopg://postgres.<project-ref>:<password>@aws-0-ap-southeast-2.pooler.supabase.com:5432/postgres
   ```
5. Paste into `backend/.env.local` as `SUPABASE_DB_URL=…`.

**If the password has URL-reserved characters** (`@ : / # ? & + % space [ ]`)
you must percent-encode them. The painless fix is to **regenerate the
database password** in Supabase Dashboard → Project Settings → Database
→ Reset database password → "Generate" — the auto-generated passwords
are URL-safe by construction.

The **service role key** (a separate credential) is found at
**Project Settings → API → Project API keys → `service_role` `secret`**.
Treat it as god-mode; it bypasses Row Level Security.

For team handoff, record both values in your team password manager —
never check `.env.local` in.

## Applying the schema

```bash
psql "$SUPABASE_DB_URL_PLAIN" -f src/db/schema.sql
```

Where `SUPABASE_DB_URL_PLAIN` is the same URI **without** the
`+psycopg` driver suffix — `psql` doesn't understand that part.

You can also paste the contents of `src/db/migrations/0001_initial_schema.sql`
into the Supabase Dashboard SQL Editor for a one-shot apply without
needing `psql` locally.

## LangSmith observability

Set `LANGSMITH_ENDPOINT=https://apac.api.smith.langchain.com` in
`.env.local` to route traces through LangSmith's APAC region (closer
to AU users than the US default).

Set `LANGSMITH_PROJECT=ato-assistant-dev` so this project's traces
land in their own project, not whatever LangSmith default you may
have configured elsewhere.

## Where things live

| Concern | Path |
|---|---|
| HTTP API surface | `src/api/` |
| LangGraph topology | `src/agents/graph.py` |
| Typed shared state | `src/agents/state.py` |
| Node protocol | `src/agents/node_protocol.py` |
| Audit + PII-safe logger | `src/audit/` |
| LangSmith trace redactor | `src/observability/` |
| Disclaimer templates | `src/disclaimers/` |
| Pydantic settings | `src/config/settings.py` |
| DDL + repositories | `src/db/migrations/`, `src/db/repos/` |
| Crawler / scraper / embedder | `src/ingestion/` (Phase 6/7) |
| Eval harness + golden set | `src/eval/`, `data/golden_set.yaml` (Phase 8) |
