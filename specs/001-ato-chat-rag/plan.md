# Implementation Plan: ATO Chat with Cited Answers and RAG Pipeline

**Branch**: `001-ato-chat-rag` | **Date**: 2026-06-03 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification at `/specs/001-ato-chat-rag/spec.md`

## Summary

Deliver the v1 ATO Assistant as a two-tier web application: a React +
TypeScript chat UI on Vercel and a Python (FastAPI) backend on Railway
that runs a LangGraph multi-agent pipeline over a Supabase Postgres
(pgvector) retrieval store populated by a crawl-then-scrape ingestion
module sourcing `www.ato.gov.au` HTML pages. The agent pipeline enforces
the spec's non-negotiables — PII guard before any LLM call, scope/safety
classification, citation alignment, and confidence/correctness gating —
with refusals returned whenever any gate fails. Voyage AI provides
embeddings, Anthropic Claude provides answer generation and the
dedicated boundary classifier, and LangSmith provides end-to-end
tracing. Cross-border processing is permitted per the relaxed FR-018a;
the predominant disclaimer notifies users (APP 8) and the PII guard
remains the residency-equivalent guarantee.

## Technical Context

**Language/Version**: Python 3.12 (backend); TypeScript 5.x with React
19 (frontend).

**Primary Dependencies**:
- **Backend**: FastAPI 0.115+ (HTTP + OpenAPI), LangGraph (multi-agent
  orchestration), LangChain core (model and tool primitives), anthropic
  (Claude SDK, direct API), voyageai (Voyage embeddings SDK), supabase-py
  + psycopg + SQLAlchemy 2.x (Supabase Postgres access),
  presidio-analyzer + presidio-anonymizer (PII detection and masking),
  httpx (async HTTP for crawler/scraper), trafilatura + selectolax
  (main-content extraction), protego (robots.txt parsing), langsmith
  (observability), uvicorn (ASGI server), pytest + pytest-asyncio
  (tests), ruff (lint), mypy (type checks).
- **Backend toolchain**: **UV (Astral)** manages the Python toolchain,
  the virtual environment, and dependency resolution. `pyproject.toml`
  is the source of truth for declarations; `uv.lock` is committed for
  reproducible installs. All backend commands run under `uv run …` or
  inside the venv UV provisions at `backend/.venv/`.
- **Frontend**: Next.js 16 App Router, React 19, Tailwind CSS v4,
  shadcn/ui components, Vitest + React Testing Library (unit), Playwright
  + `@axe-core/playwright` (e2e + accessibility), `eslint-plugin-jsx-a11y`
  (lint-time accessibility).

**Storage**: Supabase Postgres (Sydney, `ap-southeast-2`) with the
`pgvector` extension. All persisted state — chunks, source documents,
URL inventory, audit log, eval runs — lives in Supabase. Row-level
security disabled for the backend service-role; the React client never
queries Supabase directly.

**Testing**: pytest + pytest-asyncio for backend unit and integration;
Vitest + React Testing Library for frontend components; Playwright for
end-to-end and accessibility audits; a bespoke evaluation harness
(written in Python) that drives the chat API with the 30-question golden
set and produces a verdict report.

**Target Platform**:
- **Frontend**: Vercel (`syd1` for static and Edge; serverless functions
  for any frontend-side server routes).
- **Backend**: Railway (`asia-southeast1` Singapore — closest available
  Railway region to Australia).
- **Database**: Supabase managed (Sydney `ap-southeast-2`).
- **Embedding service**: Voyage AI managed API (provider-default region).
- **LLM**: Anthropic Claude direct API (provider-default region).
- **Observability**: LangSmith managed (provider-default region).

**Project Type**: Web application (frontend + backend split).

**Performance Goals**: Per SC-008, P50 ≤ 5 s and P95 ≤ 10 s for the
end-to-end answer or refusal turn. Token-budget cap of 6 k input tokens
to Claude per turn. Crawler default rate: 1 request/second per
`www.ato.gov.au`.

**Constraints**:
- **Citation correctness 100% / hallucinated citations 0%** (SC-001,
  SC-002 — zero tolerance).
- **PII to LLM 0%** (SC-006 — zero tolerance; PII guard fails closed per
  FR-009a).
- **WCAG 2.2 AA** (FR-011a, SC-011) verified by automated audits in CI.
- **Corpus is `www.ato.gov.au` HTML only** (FR-012) — the retrieval
  query MUST hard-filter by source domain.
- **Cross-border processing allowed** (FR-018a as relaxed) with the
  predominant disclaimer carrying the APP 8 notice.

**Scale/Scope**: Internal development preview for v1; not yet sized for
production traffic. Initial corpus estimate: ~5-15 k pages on
`www.ato.gov.au`, ~50-150 k chunks at ~500 tokens/chunk. Golden eval set:
30 questions. No locked concurrency target; expect single-digit
concurrent users for the v1 preview.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Each principle is enumerated below with how this plan complies. No
violations.

- **I. Spec-Driven Development** — ✅ This plan is produced from
  `spec.md` (ratified) and traces every artifact to a numbered FR or SC.
  No code will be authored before the corresponding spec sections are
  resolved.
- **II. Test-First Development (NON-NEGOTIABLE)** — ✅ The tasks list
  produced by `/speckit.tasks` will schedule one or more failing tests
  before any implementation task within each user story (Red-Green-
  Refactor). The bespoke evaluation harness (Phase 1 contract +
  `/eval`-tagged tasks) gates CI; it must run green for any change that
  touches retrieval, generation, citation, or PII.
- **III. Clear Naming & Explicit Interfaces** — ✅ Each LangGraph node
  is implemented as a separate Python module with a typed
  `NodeProtocol`. The frontend exposes one HTTP contract
  (`contracts/api-chat.openapi.yaml`); the backend exposes typed
  service interfaces between modules; the crawler emits a versioned
  JSON-schema inventory (`contracts/url-inventory.schema.json`). Domain
  names (`TFN`, `ABN`, `BAS`, `GST`, `PAYG`) are preserved verbatim.
- **IV. Single Responsibility Principle** — ✅ Each RAG stage lives in
  its own module: `ingestion/crawler/`, `ingestion/scraper/`,
  `ingestion/embedder/`, `agents/input_guard/` (PII + scope/safety in
  separate sub-modules), `agents/retrieval/`, `agents/generation/`,
  `agents/citation_check/`, `agents/scoring/`, `api/`, `audit/`,
  `eval/`. No module accumulates a second responsibility.
- **V. Grounded Answers with Verifiable Citations (NON-NEGOTIABLE)** —
  ✅ The citation-verification agent (FR-013) hard-rejects any generated
  answer whose citation set does not resolve to chunks present in the
  retrieval result. The retrieval index is domain-filtered to
  `www.ato.gov.au`. Refusal is the default whenever a gate fails. No
  non-ATO source can enter the answering path.

**Additional Constraints (RAG Pipeline & Domain) check**:
- **Source authority** — ✅ FR-012 + crawler/scraper provenance
  (`source_url`, `fetched_at`, `content_hash`, `last_modified`) per
  chunk.
- **Provenance & audit** — ✅ FR-017 audit record persisted per turn;
  data-model.md schemas in Phase 1.
- **Privacy & PII** — ✅ Presidio + custom recognizers + fail-closed
  scanner per FR-009a; APP 8 disclosure on predominant disclaimer per
  the relaxed FR-018a. LangSmith traces receive only PII-redacted
  state — the PII guard runs before any field is written to the shared
  LangGraph state that the tracer captures, so the constitution's
  "no PII to third-party analytics tooling" rule holds.
- **Refusal behavior** — ✅ Each refusal carries a distinct reason code;
  no partial answers in refusals.
- **Model & retrieval transparency** — ✅ `/system-info` endpoint
  reports LLM identity+version, embedding model identity+version, index
  version, and last refresh timestamp.

**Gate result**: PASS. Proceed to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/001-ato-chat-rag/
├── plan.md                              # This file (/speckit-plan output)
├── spec.md                              # Feature spec (already authored)
├── research.md                          # Phase 0 — technology decisions and rationale
├── data-model.md                        # Phase 1 — entity-to-schema mapping
├── quickstart.md                        # Phase 1 — local dev setup
├── contracts/                           # Phase 1 — external interface contracts
│   ├── api-chat.openapi.yaml            # POST /chat + /system-info HTTP contract
│   └── url-inventory.schema.json        # Crawler output schema
├── checklists/
│   └── requirements.md                  # Spec quality checklist (already passing)
└── tasks.md                             # Created by /speckit-tasks (next phase)
```

### Source Code (repository root)

```text
backend/                                 # Python 3.12, FastAPI, LangGraph
├── src/
│   ├── api/
│   │   ├── main.py                      # FastAPI app, route registration
│   │   ├── chat_route.py                # POST /chat handler
│   │   └── system_info_route.py         # GET /system-info handler
│   ├── agents/
│   │   ├── graph.py                     # LangGraph StateGraph wiring
│   │   ├── state.py                     # Typed shared state (TypedDict)
│   │   ├── input_guard/
│   │   │   ├── pii_node.py              # User-Story 2 agent: PII detection + mask/refuse
│   │   │   ├── pii_recognizers.py       # Custom Presidio recognizers (TFN, ABN)
│   │   │   ├── scope_safety_node.py     # User-Story 3 agent: rules + classifier
│   │   │   └── deterministic_rules.py   # Non-English, banned-keyword pre-filter
│   │   ├── retrieval/
│   │   │   ├── retrieval_node.py        # User-Story 1 retrieval agent
│   │   │   └── pgvector_client.py       # Supabase pgvector queries
│   │   ├── generation/
│   │   │   └── generation_node.py       # Claude call with retrieved context
│   │   ├── citation_check/
│   │   │   ├── citation_node.py         # Citation-alignment verification agent
│   │   │   └── url_resolver.py          # Live-URL check for cited URLs
│   │   └── scoring/
│   │       └── scoring_node.py          # Confidence + correctness grading agent
│   ├── ingestion/
│   │   ├── crawler/
│   │   │   ├── crawl.py                 # User-Story 4 — leaf-URL inventory
│   │   │   ├── robots.py                # protego wrapper
│   │   │   └── rate_limiter.py          # Polite per-host rate limit
│   │   ├── scraper/
│   │   │   ├── scrape.py                # User-Story 5 — fetch + extract
│   │   │   ├── extractor.py             # Main-content extraction (trafilatura)
│   │   │   └── chunker.py               # Token-aware chunking
│   │   └── embedder/
│   │       └── voyage_embedder.py       # Voyage AI client + batch embed
│   ├── audit/
│   │   ├── audit_writer.py              # FR-017 persistence
│   │   └── pii_safe_logger.py           # FR-009 plaintext-PII gate
│   ├── disclaimers/
│   │   └── templates.py                 # Predominant + per-answer disclaimer text
│   ├── eval/
│   │   ├── harness.py                   # User-Story 6 — golden-set runner
│   │   ├── golden_set.py                # Loader for golden_set.yaml
│   │   ├── scorers.py                   # Citation-correctness, refusal-correctness, groundedness
│   │   └── report.py                    # Aggregate report writer
│   ├── db/
│   │   ├── schema.sql                   # Postgres + pgvector DDL
│   │   ├── migrations/                  # Versioned migrations
│   │   └── repos/                       # Typed repositories per entity
│   └── config/
│       └── settings.py                  # Env-backed Pydantic settings
├── tests/
│   ├── contract/                        # OpenAPI conformance tests
│   ├── integration/                     # Multi-agent flows against test DB
│   └── unit/
├── data/
│   └── golden_set.yaml                  # 30 question/expected-answer/expected-citation triples
├── pyproject.toml
└── README.md

frontend/                                # Next.js 16, React 19, TypeScript
├── src/
│   ├── app/
│   │   ├── layout.tsx                   # Predominant disclaimer in shell
│   │   ├── page.tsx                     # Chat page
│   │   └── api/                         # Optional Vercel-side routes (auth, telemetry proxy)
│   ├── components/
│   │   ├── ChatPanel.tsx                # Streamed answer rendering
│   │   ├── PredominantDisclaimer.tsx
│   │   ├── PerAnswerDisclaimer.tsx
│   │   ├── CitationList.tsx
│   │   ├── ConfidenceBadge.tsx
│   │   └── RefusalCard.tsx
│   ├── lib/
│   │   ├── chatClient.ts                # Typed fetch wrapper for POST /chat
│   │   └── types.ts                     # Mirror of OpenAPI types
│   └── styles/
│       └── globals.css
├── tests/
│   ├── unit/                            # Vitest + RTL
│   └── e2e/                             # Playwright + @axe-core/playwright
├── package.json
└── next.config.ts
```

**Structure Decision**: Web application (frontend + backend split) per
plan-template Option 2. The two tiers deploy to separate platforms
(Vercel and Railway) and communicate over the HTTP contract defined in
`contracts/api-chat.openapi.yaml`. The split is justified by the spec's
distinct execution shapes: the backend hosts long-running LangGraph
orchestrations and the ingestion pipeline; the frontend is a thin,
accessible chat UI.

## Complexity Tracking

> No Constitution Check violations require justification.

A small number of stack-driven decisions are worth surfacing for
reviewer awareness, even though none break a principle:

| Decision | Why this choice | Simpler alternative — and why rejected |
|---|---|---|
| Railway in Singapore for the backend (no AU region available) | Closest Railway region to AU users; preserves user's stated PaaS choice; FR-018a relaxed to permit cross-border. | Fly.io Sydney — rejected because user explicitly named Railway. APP 8 notice on the predominant disclaimer covers the cross-border disclosure. |
| Voyage AI managed API (US-hosted) | User-specified embedding provider; strong domain-tuned options (e.g., `voyage-3-large`, `voyage-law-2`). | AU-deployed Voyage via AWS Marketplace — rejected for v1 because user did not require AU residency. Public ATO content embeddings carry no PII. |
| LangSmith managed (US-hosted) | User-specified observability; minimal-config tracing for every LangGraph node. | Self-hosted LangSmith on AWS Sydney — rejected for v1 because user did not require AU residency. **PII guard fails closed before any data reaches LangSmith.** |
| Anthropic Claude direct API (US-hosted) | User-selected provider/region. | Bedrock Sydney — rejected because user explicitly chose direct API. |
| LangGraph as the orchestrator | Matches the user's "land graph" requirement; deterministic graph topology + per-node tracing in LangSmith; SRP-friendly. | Plain sequential Python with no framework — rejected because losing LangSmith node-level tracing makes Principle V regressions much harder to catch. |
| Supabase pgvector (single store) | One database, AU residency, OLTP + vector in one place; simpler ops. | Separate vector DB (e.g., Weaviate, Qdrant) — rejected because Supabase covers v1 corpus size; no need to add a second vendor. |
