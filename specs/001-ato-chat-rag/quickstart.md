# Quickstart: ATO Assistant — local development

**Phase 1 output** — minimal viable local setup for running the
backend, frontend, and ingestion pipeline against a Supabase project.
This is the path a new contributor follows before opening their first
PR. The numbered FRs and the spec live at [`spec.md`](./spec.md); the
architecture lives at [`plan.md`](./plan.md).

## Prerequisites

- macOS, Linux, or WSL2.
- **UV (Astral)** on PATH — install with
  `curl -LsSf https://astral.sh/uv/install.sh | sh`. UV provisions the
  required Python toolchain (3.12) automatically.
- Node.js 20.x, Bun (optional), and Git on PATH.
- A Supabase project in the Sydney region (`ap-southeast-2`) — free
  tier is enough for development.
- API keys: Anthropic, Voyage AI, LangSmith. Stored locally in
  `backend/.env.local`; **never** committed.
- `psql` client (for the one-shot DDL apply).

## One-time setup

### 1. Clone and branch

```bash
git clone <repo-url>
cd ato-assistant-opus-spdd
git checkout 001-ato-chat-rag
```

### 2. Backend

```bash
cd backend
uv python install 3.12         # install Python 3.12 if not present
uv sync --all-extras           # creates .venv, resolves deps from pyproject.toml + uv.lock, installs dev extras
cp .env.example .env.local
# Edit .env.local with the keys below.
```

> `uv sync` creates and populates `backend/.venv/` automatically — no
> manual `python -m venv` step. You can activate it with
> `source .venv/bin/activate` if you prefer, but `uv run <cmd>` works
> without activation.

Required environment variables (`backend/.env.local`):

```
SUPABASE_DB_URL=postgresql://...
SUPABASE_SERVICE_ROLE_KEY=...
ANTHROPIC_API_KEY=sk-ant-...
VOYAGE_API_KEY=...
LANGSMITH_API_KEY=...
LANGCHAIN_PROJECT=ato-assistant-dev
LANGCHAIN_TRACING_V2=true
```

### 3. Database schema

```bash
psql "$SUPABASE_DB_URL" -f src/db/schema.sql
psql "$SUPABASE_DB_URL" -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### 4. Seed corpus (User Story 1 MVP)

Until the crawler is run end-to-end, the MVP seed corpus is loaded
from `backend/data/seed_corpus/*.html`:

```bash
uv run python -m src.ingestion.seed_corpus_loader
```

This populates `source_document` and `chunk` for a small hand-curated
set of ATO pages so User Story 1 is independently testable.

### 5. Frontend

```bash
cd ../frontend
npm install
cp .env.example .env.local
# Set NEXT_PUBLIC_BACKEND_BASE_URL=http://localhost:8000
```

## Run locally

Two terminals:

```bash
# Terminal 1 — backend
cd backend
uv run uvicorn src.api.main:app --reload --port 8000
```

```bash
# Terminal 2 — frontend
cd frontend
npm run dev    # http://localhost:3000
```

Open `http://localhost:3000`. The predominant disclaimer should be the
first thing visible on the page.

## Smoke test (manual)

1. Submit a known-good question (e.g., "What is the tax-free
   threshold?"). Expect: an answer with at least one citation linking
   to `www.ato.gov.au`, the per-answer disclaimer, and a confidence
   badge.
2. Submit a question outside the corpus (e.g., "What's the GST in New
   Zealand?"). Expect: a refusal with reason `out-of-scope`.
3. Submit a question with PII integral to the meaning (e.g., "What is
   the tax on $90,000 earned by Jane Citizen, TFN 123 456 782?").
   Expect: a refusal with reason `pii-integral`.

## Run the full ingestion pipeline (User Stories 4 + 5)

```bash
cd backend
# Crawl - produce the URL inventory.
uv run python -m src.ingestion.crawler.crawl \
  --seed https://www.ato.gov.au/individuals/ \
  --depth 4 \
  --rate-limit 1.0 \
  --output data/inventories/run-$(date +%Y%m%d-%H%M%S).json

# Scrape + embed - populate source_document + chunk.
uv run python -m src.ingestion.scraper.scrape \
  --inventory data/inventories/<run>.json
```

The crawler output is validated against
[`contracts/url-inventory.schema.json`](./contracts/url-inventory.schema.json)
before any scrape step runs.

## Run the evaluation harness (User Story 6)

```bash
cd backend
uv run python -m src.eval.harness \
  --golden-set data/golden_set.yaml \
  --report-dir reports/eval-$(date +%Y%m%d-%H%M%S)
# Exit code 0 = all thresholds met; non-zero = at least one threshold missed.
```

## Tests

```bash
# Backend
cd backend && uv run pytest

# Frontend
cd frontend && npm test        # Vitest (unit)
cd frontend && npm run e2e     # Playwright (e2e + a11y)
```

CI runs all of the above plus an OpenAPI drift check against
[`contracts/api-chat.openapi.yaml`](./contracts/api-chat.openapi.yaml)
and the evaluation harness gate.

## Deployment

- **Frontend → Vercel**: Vercel Git integration. Preview deploy per PR;
  production on `main`. Region: `syd1`.
- **Backend → Railway**: Railway Git integration. Region:
  `asia-southeast1` (Singapore — closest available to AU). Railway's
  Nixpacks builder auto-detects `backend/uv.lock` and installs with UV;
  no custom build hook required.
- **Database → Supabase**: Sydney `ap-southeast-2`. Migrations applied
  via CI on merge to `main`.
- Environment variables (above) are configured in each PaaS's secrets
  UI.

## Where things live in code

| Concern | Path |
|---|---|
| HTTP API surface | `backend/src/api/` |
| LangGraph topology | `backend/src/agents/graph.py` |
| PII guard | `backend/src/agents/input_guard/pii_*` |
| Scope / safety classifier | `backend/src/agents/input_guard/scope_safety_node.py` |
| Retrieval | `backend/src/agents/retrieval/` |
| Generation | `backend/src/agents/generation/` |
| Citation verification | `backend/src/agents/citation_check/` |
| Confidence + correctness scoring | `backend/src/agents/scoring/` |
| Crawler | `backend/src/ingestion/crawler/` |
| Scraper | `backend/src/ingestion/scraper/` |
| Embedder | `backend/src/ingestion/embedder/` |
| Audit log writer | `backend/src/audit/` |
| Golden set + eval harness | `backend/data/golden_set.yaml`, `backend/src/eval/` |
| Chat UI | `frontend/src/app/`, `frontend/src/components/` |
