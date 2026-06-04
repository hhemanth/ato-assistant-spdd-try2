# Research: ATO Chat with Cited Answers and RAG Pipeline

**Phase 0 output** — captures the technology decisions, the rationale
for each, and the alternatives that were considered and rejected. All
`NEEDS CLARIFICATION` markers from earlier phases are resolved here.

## Decisions

### Backend framework — FastAPI 0.115+

- **Decision**: FastAPI on Python 3.12.
- **Rationale**: Async-first matches LangGraph's I/O-heavy nodes (LLM,
  embedding, DB calls); automatic OpenAPI generation lets the
  `contracts/api-chat.openapi.yaml` artifact be reproduced from the live
  app for drift detection; first-class Pydantic v2 typing aligns with
  Principle III (explicit interfaces).
- **Alternatives considered**: Flask (rejected — no native async; no
  OpenAPI gen). Litestar (rejected — smaller ecosystem; LangGraph
  examples favor FastAPI). Django REST (rejected — sync-default; ORM
  overhead unnecessary, Supabase already provides DB).

### Multi-agent orchestrator — LangGraph

- **Decision**: LangGraph `StateGraph` with a typed shared `State`
  TypedDict; nodes implement the user's five agents plus an implicit
  `generation` node between retrieval and citation-check.
- **Rationale**: User requirement. Per-node tracing in LangSmith is
  near-zero-config and gives the eval harness a stable seam for
  measuring per-stage failure. Conditional edges express the "refuse on
  any guard fail" topology cleanly.
- **Alternatives considered**: Plain Python sequential pipeline
  (rejected — loses node-level tracing). LangChain Agents (rejected —
  less explicit control flow; harder to reason about Principle V
  enforcement). CrewAI (rejected — user specified LangGraph).

### LangGraph node topology

```text
START
  → input_guard.pii_node              (PII detection + mask/refuse — Agent 4)
  → input_guard.scope_safety_node     (Rules + classifier — Agent 5)
  → retrieval_node                    (Agent 1, retrieval half)
  → generation_node                   (Agent 1, generation half; implicit)
  → citation_check_node               (Agent 3)
  → scoring_node                      (Agent 2)
  → finalize_node                     (attach disclaimer + badge + audit)
END
```

- Any guard failure routes to a single `refusal_node` and terminates
  with a typed `Refusal` payload carrying a distinct reason code.
- The user listed five agents; the topology adds one implicit
  `generation_node` so retrieval (data gathering) and generation
  (answer drafting) remain single-responsibility per Principle IV.

### LLM provider — Anthropic Claude direct API

- **Decision**: Claude Sonnet 4.6 for generation and the boundary
  classifier; Claude Haiku 4.5 for cheaper deterministic checks
  (refusal triage, low-latency confidence-grade calls).
- **Rationale**: User selection. Sonnet 4.6 is the current
  best-balance-of-cost-and-quality model; Haiku 4.5 is materially
  cheaper for non-critical-path calls; both support structured outputs
  for clean inter-node contracts.
- **Alternatives considered**: Claude Opus 4.7 (rejected for v1 — cost
  per turn unjustified at preview scale; revisit after eval baseline).
  GPT-class models (rejected — user chose Anthropic).

### Embeddings — Voyage AI

- **Decision**: `voyage-3-large` as primary embedding for ATO content
  chunks and user queries; document hash-keyed cache to avoid
  re-embedding unchanged chunks.
- **Rationale**: User selection. `voyage-3-large` is Voyage's current
  general-purpose top-of-line embedding with strong retrieval
  performance.
- **Alternatives considered**: `voyage-law-2` (rejected as primary —
  legal corpus tuning may help on ATO ruling-style content, but
  evaluating it against `voyage-3-large` is a v2 task once the eval
  harness is stable). OpenAI `text-embedding-3-large` (rejected — user
  chose Voyage).

### Database — Supabase Postgres + pgvector

- **Decision**: Single Supabase project in the Sydney region
  (`ap-southeast-2`). The `pgvector` extension stores chunk embeddings
  alongside the source-document and audit relational tables.
- **Rationale**: One database for OLTP + vector reduces operational
  surface. Sydney region keeps AU residency where the project can
  cheaply have it (audit log, index storage). The Postgres `vector`
  column type with HNSW index gives sub-100 ms top-k retrieval at v1
  scale (≤ 150 k chunks).
- **Alternatives considered**: Pinecone / Qdrant / Weaviate (rejected —
  adds a second vendor for no v1 benefit). Self-hosted Postgres
  (rejected — Supabase already managed). Supabase IVFFlat instead of
  HNSW (rejected — HNSW has better recall at the cost of more memory,
  acceptable for v1).

### PII detection — Microsoft Presidio + custom recognizers

- **Decision**: `presidio-analyzer` with Microsoft's built-in
  recognizers for `EMAIL_ADDRESS`, `PHONE_NUMBER`, `DATE_TIME`,
  `LOCATION`, `PERSON`; custom recognizers for `AU_TFN` (TFN), `AU_ABN`
  (ABN), `AU_ACN`, plus a confidence-threshold-based "incidental vs
  integral" gate.
- **Rationale**: Open-source, in-process (no PII crosses a network
  boundary during detection), AU-specific recognizers are
  straightforward to author with checksum verification (TFN check digit,
  ABN modulus). Fail-closed per FR-009a is implemented by treating any
  analyzer exception or sub-threshold result as a refusal.
- **Alternatives considered**: AWS Comprehend PII (rejected — adds
  cross-border call before the LLM call, doesn't make residency simpler
  even under relaxed FR-018a). Pure regex (rejected — fails recall on
  PERSON, LOCATION, and partial identifiers; brittle).

### Refusal classifier — deterministic rules + Claude Haiku boundary classifier

- **Decision**: Two layers per FR-010a. Layer 1: deterministic rules
  (non-English detection via `langdetect`, banned-keyword sets,
  obvious-illegal pattern matches) run in-process with no model call.
  Layer 2: a Claude Haiku 4.5 call with a constrained JSON-schema
  output (`{ "verdict": "in_scope" | "out_of_scope" | "inappropriate" |
  "personal_advice", "confidence": float }`) for boundary cases.
- **Rationale**: Rules give determinism and cost-zero handling of the
  unambiguous cases; the classifier gives the necessary semantic
  judgment for boundary phrasing (e.g., personal-advice vs general
  knowledge). The classifier is independently versioned (model + system
  prompt + schema all under version control), independently testable
  (golden eval set tags refusal cases), and crucially **not** the
  answering LLM.
- **Alternatives considered**: Single-LLM self-classification
  (rejected — couples refusal accuracy to answering-model drift, weakens
  the eval gate). Pure rules (rejected — boundary recall too low).

### Citation verification

- **Decision**: Two checks combined.
  1. **Alignment check** (deterministic) — every citation URL emitted by
     the generation node MUST be present in the set of source URLs
     returned by `retrieval_node`. URLs absent from the retrieval set
     fail the answer and trigger a `citation-misalignment` refusal.
  2. **Liveness check** (sampled) — for cited URLs, issue an
     in-process HEAD request with a 2 s timeout. If the URL returns a
     non-2xx status, log a freshness incident and refuse rendering with
     a `stale-source` reason code.
- **Rationale**: Principle V is zero-tolerance for fabricated citations.
  Pure LLM-as-judge is insufficient — deterministic URL set membership
  is the strongest guarantee available. Liveness avoids serving answers
  whose underlying source has moved or been removed.
- **Alternatives considered**: LLM-as-judge only (rejected — risks
  silent agreement with hallucinations).

### Scoring (confidence + correctness)

- **Decision**: Composite scoring.
  - **Confidence** = `α · max(retrieval_similarity)` + `(1 − α) ·
    1[generation_finished_naturally]`. `α` defaults to 0.7;
    configurable.
  - **Correctness** = fraction of the answer's factual sentences for
    which the cited URLs include at least one chunk whose snippet
    lexically supports the sentence (BM25 over the chunk text,
    threshold-based).
  - Below-threshold answers refused per FR-015. User-facing badge maps
    to coarse High / Medium / Low buckets.
- **Rationale**: Composite scoring uses signals available without an
  additional LLM call, keeps grading deterministic and explainable, and
  surfaces threshold tuning to the eval harness. Numeric scores are
  persisted in the audit record for incident review.
- **Alternatives considered**: LLM-as-judge correctness (rejected as
  primary — adds cost, non-determinism, and couples grading to model
  drift). Generation log-probabilities (considered as a v2 add — not
  yet exposed by the Anthropic API in a useful per-claim form).

### Ingestion — crawler

- **Decision**: Async crawler built on `httpx.AsyncClient` with
  `protego` for `robots.txt` parsing and an in-memory token-bucket rate
  limiter (default 1 req/s, configurable per-host). Depth-bounded BFS
  from seed URLs (default depth 6). Discovered URLs normalized
  (lowercase scheme/host, strip session params, strip fragments, sort
  query params) before dedup. Leaf classification: a page is a leaf
  when it contains ≥ N tokens of extracted main content (`N = 250`
  default) and is not a search/listing page (URL pattern blacklist).
- **Rationale**: Stays well under any reasonable host load,
  deterministic dedup, respects ATO's robots policy, and avoids
  crawler-trap infinite loops by depth bound + URL normalization.
- **Alternatives considered**: Scrapy (rejected — heavyweight; async-
  unfriendly mid-pipeline; harder to integrate inside FastAPI test
  fixtures). Playwright-rendered crawl (rejected — `www.ato.gov.au`
  serves static HTML for content pages; JS rendering would add cost
  without benefit).

### Ingestion — scraper

- **Decision**: For each leaf URL, fetch with `httpx`, run `trafilatura`
  to extract main content, then chunk with a token-aware splitter
  (`~500` tokens, `~80` token overlap, paragraph boundaries preferred).
  Each chunk is embedded with Voyage `voyage-3-large` and inserted with
  full provenance (`source_url`, `fetched_at`, `content_hash`,
  `source_last_modified`). Re-scrapes compare `content_hash`; unchanged
  pages are skipped; changed pages produce a new generation of chunks
  and mark prior chunks `is_superseded = true`.
- **Rationale**: `trafilatura` is the best open-source main-content
  extractor for HTML article pages and handles ATO's content patterns
  well. Token-aware chunking preserves Voyage's input budget. Content-
  hash dedup makes nightly re-crawls cheap.
- **Alternatives considered**: Beautiful Soup with custom selectors
  (rejected — brittle to ATO template changes). Fixed-character
  chunking (rejected — produces poor retrieval recall for long pages).

### Observability — LangSmith

- **Decision**: LangSmith managed; one project per environment
  (`dev`, `eval`, `preview`); `LANGCHAIN_TRACING_V2=true` enabled in
  the backend. Trace payload redaction: any field flagged by the PII
  guard is replaced with the same redaction token used downstream so
  LangSmith never receives plaintext PII.
- **Rationale**: User requirement. The PII guard runs before any state
  field is written; LangSmith traces inherit the redacted view.
- **Alternatives considered**: OpenTelemetry + self-hosted backend
  (rejected — user chose LangSmith).

### Frontend — Next.js 16 + Tailwind v4 + shadcn/ui

- **Decision**: Next.js 16 App Router with React 19; Tailwind CSS v4;
  shadcn/ui components for the chat shell and Radix primitives for
  accessibility. Streamed answers via Server-Sent Events from the
  backend's `POST /chat` endpoint to keep TTFB low.
- **Rationale**: Vercel-native; shadcn/ui's Radix-based components are
  WCAG-friendly out of the box; SSE keeps the chat reactive without
  WebSocket complexity.
- **Alternatives considered**: Plain React with Vite (rejected — loses
  Vercel-native features and SSR/edge options that aid Core Web
  Vitals). Remix (rejected — less mature Vercel integration than Next
  in 2026).

### Accessibility — WCAG 2.2 AA gate

- **Decision**: `@axe-core/playwright` runs against every primary route
  in CI; zero AA violations is a release gate (SC-011). Manual
  screen-reader smoke test (VoiceOver + NVDA) on each release.
- **Rationale**: Automated tooling catches the bulk of structural and
  contrast issues; manual screen-reader testing catches semantic gaps
  the automated tooling cannot.
- **Alternatives considered**: Lighthouse-only (rejected — coverage
  weaker than axe-core on ARIA/structure). Manual-only (rejected — no
  regression catch in CI).

### Testing strategy

- **Backend unit**: pytest with `pytest-asyncio` for nodes and modules.
- **Backend integration**: pytest with a real Supabase test schema +
  seeded chunks + mocked Voyage/Anthropic via `respx` for cost control.
- **Backend contract**: validate the live FastAPI app's generated
  OpenAPI against `contracts/api-chat.openapi.yaml` (drift fails CI).
- **Frontend unit**: Vitest + React Testing Library for components.
- **Frontend e2e**: Playwright tests covering: cited-answer flow,
  refusal flow, PII-integral refusal flow, predominant disclaimer
  visibility, per-answer disclaimer visibility, WCAG 2.2 AA audit.
- **Evaluation harness**: Python CLI that loads
  `backend/data/golden_set.yaml`, hits the chat API, scores each
  question, and emits an aggregate report + per-question detail. CI
  invokes the harness on every PR touching retrieval/generation/
  citation; non-zero exit blocks merge.

### Backend package and toolchain manager — UV (Astral)

- **Decision**: Use UV for Python toolchain install, virtualenv
  management, dependency resolution, and lockfile generation. Source of
  truth is `backend/pyproject.toml` (PEP 621); `backend/uv.lock` is
  committed and authoritative for reproducible installs in CI and on
  Railway.
- **Rationale**: Markedly faster install + resolution than pip; native
  `uv.lock` gives reproducible builds without extra tooling; `uv run`
  removes the need to manage activation in CI and scripts; Railway's
  Nixpacks builder detects `uv.lock` and installs accordingly with no
  custom build hook needed.
- **Alternatives considered**: pip + `pip-tools` + manual `venv`
  (rejected — slower, no built-in lockfile workflow, more moving
  parts). Poetry (rejected — slower than UV, splits source-of-truth
  between `pyproject.toml` and Poetry's own resolver semantics).
  Pipenv (rejected — declining maintenance and slower).

### Configuration & secrets

- **Decision**: Environment variables only; loaded via Pydantic
  `BaseSettings`. Secrets (`ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`,
  `LANGSMITH_API_KEY`, `SUPABASE_SERVICE_ROLE_KEY`,
  `SUPABASE_DB_URL`) sourced from Railway secrets in production and
  `.env.local` in development. The frontend reads only a single
  `NEXT_PUBLIC_BACKEND_BASE_URL` — no secrets in the browser.
- **Rationale**: One source of truth; standard PaaS pattern; no secret
  in client bundles.

### CI/CD

- **Decision**: GitHub Actions. Pipeline: lint → unit → integration
  (Supabase test schema) → contract drift → eval harness (on
  retrieval/generation/citation diffs) → Playwright (against preview
  deploy). Frontend ships via Vercel's Git integration (preview
  deploy per PR); backend ships via Railway's GitHub integration.
- **Rationale**: Reuses each PaaS's native deploy story; CI gates
  everything that matters per Principle II and Principle V.

## Resolved clarifications

This phase introduces no new `NEEDS CLARIFICATION` markers. All
clarification items from the spec's `## Clarifications` section
(2026-06-03 session) and from the planning conversation are resolved:

| Question | Resolution |
|---|---|
| Corpus scope | `www.ato.gov.au` HTML only (spec Clarification 1). |
| Data residency | Cross-border permitted; PII guard + APP 8 notice cover the substance (spec FR-018a, relaxed). |
| PII-scanner failure mode | Fail closed (FR-009a). |
| Accessibility level | WCAG 2.2 AA (FR-011a, SC-011). |
| Refusal classifier | Rules + dedicated classifier separate from answering LLM (FR-010a). |
| LLM provider/region | Anthropic Claude direct API (this phase). |
| Backend framework | FastAPI (this phase). |
| Vector storage | Supabase pgvector (this phase). |
| Frontend framework | Next.js 16 App Router (this phase). |
| Crawler stack | httpx + protego + trafilatura (this phase). |
| Embedding model selection | `voyage-3-large` for v1 (this phase). |

## Open follow-ups (non-blocking for `/speckit.tasks`)

- Compare `voyage-law-2` against `voyage-3-large` on the golden set
  once the eval harness is stable; revisit primary embedding choice
  for v2.
- Lock concurrency / QPS targets pre-public-launch (currently
  out-of-scope; internal preview only).
- Revisit AU residency posture before any public exposure; the relaxed
  FR-018a is appropriate for v1 internal preview.
