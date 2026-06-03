---

description: "Dependency-ordered tasks for feature 001-ato-chat-rag"
---

# Tasks: ATO Chat with Cited Answers and RAG Pipeline

**Input**: Design documents from `/specs/001-ato-chat-rag/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md),
[research.md](./research.md), [data-model.md](./data-model.md),
[contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Test tasks are INCLUDED. The project constitution
(`Principle II — Test-First Development, NON-NEGOTIABLE`) mandates
TDD; every implementation task in this file is preceded by a failing
test task within the same phase.

**Organization**: Tasks are grouped by user story (from `spec.md`) so
each story can be implemented, tested, and demonstrated independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on
  incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1, US2, …);
  setup, foundational, and polish phases carry no story label
- Every implementation task includes the exact file path
- All paths are relative to the repository root

## Path Conventions

- **Backend**: `backend/src/…`, `backend/tests/…`, `backend/data/…`
- **Frontend**: `frontend/src/…`, `frontend/tests/…`
- **Database DDL**: `backend/src/db/schema.sql` and
  `backend/src/db/migrations/…`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Skeleton repos, tooling, env configuration, CI bootstrap.

- [X] T001 Create the two-tier project skeleton: `backend/` and `frontend/` directories per the project structure in `plan.md`
- [X] T002 [P] Initialize the Python 3.12 backend with UV (Astral): run `uv init --package backend/` to scaffold `pyproject.toml` with a `src/ato_assistant_backend/` layout, then declare runtime dependencies (FastAPI 0.115+, LangGraph, LangChain core, anthropic, voyageai, supabase, psycopg, SQLAlchemy 2.x, presidio-analyzer, presidio-anonymizer, httpx, trafilatura, selectolax, protego, langsmith, pydantic-settings, uvicorn) and a PEP 735 `dev` dependency group (pytest, pytest-asyncio, respx, ruff, mypy). Pin Python with `requires-python = ">=3.12,<3.13"` in `[project]` and `backend/.python-version = "3.12"`. Run `uv lock` and commit `backend/uv.lock`.
- [X] T003 [P] Initialize Next.js 16 frontend with `frontend/package.json` declaring next@16, react@19, react-dom@19, typescript@5, tailwindcss@4, shadcn-ui, vitest, @testing-library/react, @playwright/test, @axe-core/playwright, eslint, eslint-plugin-jsx-a11y, prettier
- [X] T004 [P] Configure backend lint and type-check: `backend/pyproject.toml` ruff + mypy configuration, strict mode
- [ ] T005 [P] Configure frontend lint and format: `frontend/.eslintrc.json` (with `jsx-a11y` recommended) and `frontend/.prettierrc`
- [X] T006 [P] Create environment templates: `backend/.env.example` (SUPABASE_DB_URL, SUPABASE_SERVICE_ROLE_KEY, ANTHROPIC_API_KEY, VOYAGE_API_KEY, LANGSMITH_API_KEY, LANGCHAIN_PROJECT, LANGCHAIN_TRACING_V2) and `frontend/.env.example` (NEXT_PUBLIC_BACKEND_BASE_URL)
- [X] T007 [P] Bootstrap GitHub Actions CI at `.github/workflows/ci.yml` with three jobs: `backend` (uses `astral-sh/setup-uv@v4`, runs `uv sync --all-groups`, then ruff / mypy / pytest via `uv run`), `frontend` (eslint, vitest, playwright), `contracts` (OpenAPI drift check). Cache `~/.cache/uv` keyed on `backend/uv.lock`. Initial jobs run lint only; test gates added in later phases.
- [X] T008 [P] Add pre-commit configuration at `.pre-commit-config.yaml` covering ruff, mypy (manual stage), eslint, prettier, end-of-file-fixer, trailing-whitespace
- [X] T009 Create Supabase project in `ap-southeast-2` (Sydney) and record connection string in the team password manager; document in `backend/README.md` how to obtain the connection string for local dev

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user
story can be implemented. Includes the database schema, the FastAPI
skeleton, the LangGraph state shape, the audit writer, the
disclaimers, and the LangSmith redaction utility.

**⚠️ CRITICAL**: No user-story work can begin until this phase is
complete.

- [X] T010 Verify Voyage AI's current default embedding dimension for `voyage-3-large` against Voyage's docs; record finding in `backend/src/db/migrations/0001_initial_schema.sql` header comment and use that dimension in `VECTOR(N)` columns. **Rationale**: gets ahead of the Phase 1/advisor-flagged dimension assumption before any retrieval test relies on it.
- [X] T011 Author the initial Postgres + pgvector DDL at `backend/src/db/migrations/0001_initial_schema.sql` covering all tables in `data-model.md`: `source_document`, `chunk`, `url_inventory`, `crawl_run`, `query`, `retrieval`, `answer`, `citation`, `refusal`, `audit_record`, `eval_question`, `eval_run`, `eval_result`. Include `CREATE EXTENSION IF NOT EXISTS vector;` and the HNSW index on `chunk.embedding`.
- [X] T012 Add a `node_invocation` table to `backend/src/db/migrations/0001_initial_schema.sql` capturing per-node model identity, model version, processing region, and timing for every LangGraph node invocation that calls a model (gap flagged at the end of Phase 1 planning).
- [X] T013 Author `backend/src/db/schema.sql` as a one-shot apply script that concatenates all migrations for local dev (`psql -f schema.sql`)
- [X] T014 [P] Create typed repository modules in `backend/src/db/repos/` — one file per entity (`source_document.py`, `chunk.py`, `query.py`, `answer.py`, `citation.py`, `refusal.py`, `audit_record.py`, `node_invocation.py`, `url_inventory.py`, `crawl_run.py`, `eval_*.py`), each exposing typed CRUD and the entity-specific lookups required by the spec FRs
- [X] T015 [P] Implement Pydantic settings module at `backend/src/config/settings.py` loading all `.env` variables with explicit types and required-field validation
- [X] T016 [P] Implement the FastAPI app skeleton at `backend/src/api/main.py` with health and version endpoints, CORS configured for the frontend origin, structured logging middleware, and OpenAPI metadata sourced from `pyproject.toml`
- [X] T017 [P] Define the typed shared LangGraph state at `backend/src/agents/state.py` (TypedDict: `query_id`, `session_id`, `masked_text`, `pii_detected`, `pii_outcome`, `scope_verdict`, `retrieval_id`, `retrieved_chunks`, `generated_text`, `citations`, `confidence`, `correctness`, `refusal`, …)
- [X] T018 [P] Implement the audit writer at `backend/src/audit/audit_writer.py` recording every turn per FR-017 plus the processing-region fields required by FR-018a (`llm_region`, `embedding_region`, `observability_region`)
- [X] T019 [P] Implement the PII-safe logger at `backend/src/audit/pii_safe_logger.py` that refuses to write any redaction-tokenized field's pre-mask value (used by all downstream loggers)
- [X] T020 [P] Implement the LangSmith trace-redaction wrapper at `backend/src/observability/langsmith_redactor.py` that replaces any state field containing PII with the redaction token before tracing
- [X] T021 [P] Author disclaimer templates at `backend/src/disclaimers/templates.py` with two strings: `PREDOMINANT` (APP 8 cross-border notice + general scope-and-purpose statement) and `PER_ANSWER` ("This information is sourced from ato.gov.au and is not personal advice — consult a registered tax agent for advice on your specific situation"). Both versioned (`DISCLAIMER_VERSION` constant).
- [X] T022 [P] Define typed protocol for LangGraph nodes at `backend/src/agents/node_protocol.py` — a `Protocol` class declaring `name`, `model_identity` (Optional), `model_version` (Optional), and `__call__(state) -> state` so each node has an explicit, testable interface (Principle III)
- [X] T023 Wire an empty LangGraph `StateGraph` at `backend/src/agents/graph.py` that imports all node placeholders, declares the topology from `research.md` (input_guard.pii → input_guard.scope_safety → retrieval → generation → citation_check → scoring → finalize), and exposes `build_graph()` returning a compiled graph
- [X] T024 Implement the refusal-routing helper at `backend/src/agents/refusal_router.py` (a conditional edge that routes to a single `refusal_node` whenever `state["refusal"]` is set)

**Checkpoint**: Foundation ready — user-story implementation can now begin.

---

## Phase 3: User Story 1 — Cited Answer or Refusal with Disclaimers (Priority: P1) 🎯 MVP

**Goal**: A user submits a question over a small seed corpus and either receives a grounded, citation-bearing answer (with the predominant and per-answer disclaimers visible) or a clear refusal when no source is available.

**Independent Test**: Run the seed-corpus loader, send a known in-scope question, verify the response contains a `www.ato.gov.au` citation and per-answer disclaimer; send an in-scope question with no covering source, verify refusal with reason `no-source`. Predominant disclaimer is verified visible on session entry.

### Tests for User Story 1 (write FIRST, observe FAIL before any T036+ implementation task)

- [X] T025 [P] [US1] Contract test for `POST /chat` answer shape at `backend/tests/contract/test_chat_answer_shape.py` — validates response against `contracts/api-chat.openapi.yaml` `AnswerResponse` schema
- [ ] T026 [P] [US1] Contract test for `POST /chat` refusal shape at `backend/tests/contract/test_chat_refusal_shape.py`
- [ ] T027 [P] [US1] Contract test for `GET /system-info` at `backend/tests/contract/test_system_info_shape.py`
- [X] T028 [P] [US1] Integration test — cited-answer flow over seed corpus at `backend/tests/integration/test_us1_cited_answer.py`
- [ ] T029 [P] [US1] Integration test — refusal when no source covers the query at `backend/tests/integration/test_us1_no_source_refusal.py`
- [ ] T030 [P] [US1] Integration test — refusal when citation-alignment check rejects the answer at `backend/tests/integration/test_us1_citation_misalignment_refusal.py`
- [ ] T030a [P] [US1] Integration test — `stale-source` refusal when a cited URL fails the liveness check (returns non-2xx) at `backend/tests/integration/test_us1_stale_source_refusal.py`
- [ ] T031 [P] [US1] Integration test — citation `source_url` MUST match `^https://www\.ato\.gov\.au/` at `backend/tests/integration/test_us1_citation_domain_filter.py`
- [X] T032 [P] [US1] Frontend unit test — `PredominantDisclaimer` renders at session entry at `frontend/tests/unit/PredominantDisclaimer.test.tsx`
- [X] T033 [P] [US1] Frontend unit test — `PerAnswerDisclaimer` renders alongside every answer at `frontend/tests/unit/PerAnswerDisclaimer.test.tsx`
- [X] T034 [P] [US1] Frontend e2e — cited-answer happy path at `frontend/tests/e2e/us1_cited_answer.spec.ts`
- [ ] T035 [P] [US1] Frontend e2e — refusal card displayed for no-source case at `frontend/tests/e2e/us1_refusal.spec.ts`

### Implementation for User Story 1

- [ ] T036 [P] [US1] Implement seed-corpus loader at `backend/src/ingestion/seed_corpus_loader.py` that reads HTML files from `backend/data/seed_corpus/*.html` and inserts `source_document` + `chunk` rows (uses the embedder from T038)
- [X] T037 [P] [US1] Hand-curate a seed corpus of 8-12 ATO HTML pages (tax-free threshold, income tax brackets, GST basics, BAS basics) at `backend/data/seed_corpus/` — pages saved as fetched HTML with their source URL recorded in a sibling `manifest.yaml`
- [ ] T038 [P] [US1] Implement the Voyage embedder at `backend/src/ingestion/embedder/voyage_embedder.py` — batched embeddings, returns the configured embedding dimension verified in T010
- [ ] T039 [P] [US1] Implement the pgvector retrieval client at `backend/src/agents/retrieval/pgvector_client.py` — top-k cosine search with a hard `is_superseded = false` filter and a hard `source_url LIKE 'https://www.ato.gov.au/%'` filter (FR-012)
- [ ] T040 [US1] Implement the retrieval node at `backend/src/agents/retrieval/retrieval_node.py` — embeds the query, calls the retrieval client, writes a `retrieval` row, returns updated state
- [ ] T041 [US1] Implement the generation node at `backend/src/agents/generation/generation_node.py` — calls Claude Sonnet 4.6 with a system prompt that requires inline citation markers `[1]`, `[2]`, …, and a structured JSON output schema for citations; records `node_invocation` row
- [ ] T042 [P] [US1] Implement the citation alignment check at `backend/src/agents/citation_check/citation_node.py` — deterministic URL-set-membership against the chunks returned by retrieval (FR-013); routes to refusal with reason `citation-misalignment` if any cited URL is absent
- [ ] T043 [P] [US1] Implement the URL liveness check at `backend/src/agents/citation_check/url_resolver.py` — HEAD request with 2 s timeout, marks `live`/`stale`/`unknown` per citation
- [ ] T043a [US1] Wire `stale-source` refusal: in `backend/src/agents/citation_check/citation_node.py`, when any citation's `liveness_status == 'stale'`, set `state["refusal"]` with reason `stale-source` and route via the refusal router (T024); ensure the integration test T030a passes
- [ ] T044 [US1] Implement the refusal node at `backend/src/agents/refusal_node.py` — accepts a refusal reason code from upstream, writes the `refusal` row, builds the typed refusal payload
- [ ] T045 [US1] Implement the finalize node at `backend/src/agents/finalize_node.py` — writes the `answer` row, writes `citation` rows, writes the `audit_record` row with processing-region fields, attaches the per-answer disclaimer text
- [ ] T046 [US1] Wire all of the above nodes into the graph at `backend/src/agents/graph.py` (replace the T023 placeholders) and add conditional edges for refusal routing
- [ ] T047 [US1] Implement the `POST /chat` route at `backend/src/api/chat_route.py` — accepts `ChatRequest`, invokes the LangGraph, returns `AnswerResponse` or `RefusalResponse`
- [ ] T048 [US1] Implement the `GET /system-info` route at `backend/src/api/system_info_route.py` returning the `SystemInfo` payload (LLM identity/version/region, embedding identity/version/region, observability identity/region, index version, last refresh, corpus scope)
- [ ] T049 [P] [US1] Implement the typed chat client wrapper at `frontend/src/lib/chatClient.ts` and its mirrored types at `frontend/src/lib/types.ts` (generated from / mirrored against `contracts/api-chat.openapi.yaml`)
- [ ] T050 [P] [US1] Implement `frontend/src/components/PredominantDisclaimer.tsx` rendering the disclaimer with appropriate ARIA role and contrast
- [ ] T051 [P] [US1] Implement `frontend/src/components/PerAnswerDisclaimer.tsx` rendered beneath every answer
- [ ] T052 [P] [US1] Implement `frontend/src/components/CitationList.tsx` rendering numbered links to `source_url` plus the source freshness date (FR-006)
- [ ] T053 [P] [US1] Implement `frontend/src/components/RefusalCard.tsx` rendering the refusal text + reason code in an accessible card
- [ ] T054 [US1] Implement `frontend/src/components/ChatPanel.tsx` orchestrating input, the predominant disclaimer banner, answer + citations + per-answer disclaimer, and refusal cards
- [ ] T055 [US1] Implement `frontend/src/app/layout.tsx` to mount the predominant disclaimer in the shell so it is visible before any chat input
- [ ] T056 [US1] Implement `frontend/src/app/page.tsx` rendering the `ChatPanel`

**Checkpoint**: User Story 1 (MVP) is fully functional and independently testable.

---

## Phase 4: User Story 2 — PII Detection and Masking (Priority: P2)

**Goal**: Inbound queries are scanned for PII; incidental PII is masked before any LLM call, integral PII triggers refusal, scanner failure fails closed.

**Independent Test**: Submit queries with incidental and integral PII (across email, phone, DOB, TFN, ABN); verify masking, refusals, no plaintext PII in DB, no plaintext PII in LangSmith.

### Tests for User Story 2 (write FIRST)

- [ ] T057 [P] [US2] Unit test — TFN check-digit validation at `backend/tests/unit/test_au_tfn_recognizer.py`
- [ ] T058 [P] [US2] Unit test — ABN modulus validation at `backend/tests/unit/test_au_abn_recognizer.py`
- [ ] T059 [P] [US2] Unit test — ACN checksum validation at `backend/tests/unit/test_au_acn_recognizer.py`
- [ ] T060 [P] [US2] Unit test — incidental-vs-integral classifier at `backend/tests/unit/test_pii_incidental_classifier.py`
- [ ] T061 [P] [US2] Integration test — incidental PII (email) is masked and the masked query proceeds at `backend/tests/integration/test_us2_incidental_pii_masked.py`
- [ ] T062 [P] [US2] Integration test — integral PII (TFN) triggers `pii-integral` refusal and the query is never forwarded to the LLM at `backend/tests/integration/test_us2_integral_pii_refused.py`
- [ ] T063 [P] [US2] Integration test — scanner exception triggers fail-closed `pii-scanner-fail` refusal at `backend/tests/integration/test_us2_scanner_fail_closed.py`
- [ ] T064 [P] [US2] Integration test — `audit_record` contains zero plaintext PII for any PII-tagged query at `backend/tests/integration/test_us2_no_plaintext_in_audit.py`
- [ ] T065 [P] [US2] Integration test — LangSmith traces contain zero plaintext PII (uses the redactor from T020) at `backend/tests/integration/test_us2_no_plaintext_in_traces.py`

### Implementation for User Story 2

- [ ] T066 [P] [US2] Implement the AU_TFN custom Presidio recognizer at `backend/src/agents/input_guard/pii_recognizers.py::AuTfnRecognizer` (regex + 9-digit checksum)
- [ ] T067 [P] [US2] Implement the AU_ABN custom Presidio recognizer at `backend/src/agents/input_guard/pii_recognizers.py::AuAbnRecognizer` (11-digit modulus 89)
- [ ] T068 [P] [US2] Implement the AU_ACN custom Presidio recognizer at `backend/src/agents/input_guard/pii_recognizers.py::AuAcnRecognizer`
- [ ] T069 [US2] Implement the incidental-vs-integral classifier at `backend/src/agents/input_guard/pii_intent_classifier.py` — heuristic over PII span + question dependency, with a Claude Haiku fallback for ambiguous cases
- [ ] T070 [US2] Implement the PII guard node at `backend/src/agents/input_guard/pii_node.py` — runs Presidio with the custom recognizers, applies redaction tokens for incidental PII, sets `pii_outcome` in state, routes to refusal for integral PII or scanner failure (fail-closed per FR-009a)
- [ ] T071 [P] [US2] Implement the redaction token replacement utility at `backend/src/agents/input_guard/redaction.py` — replaces detected spans with `<REDACTED:CLASS>` tokens; idempotent
- [ ] T072 [US2] Add `query.masked_text`, `query.pii_detected`, `query.pii_outcome`, `query.pii_scanner_version` writes to the `query` repository (T014) so they are populated on every turn

**Checkpoint**: User Story 2 in place; SC-006 (zero unmasked PII to LLM) is enforced.

---

## Phase 5: User Story 3 — Scope and Content-Safety Refusal (Priority: P2)

**Goal**: Out-of-scope, inappropriate, and personal-advice queries are detected and refused before retrieval, using deterministic rules plus a dedicated classifier separate from the answering LLM (FR-010a).

**Independent Test**: Run the curated boundary set (out-of-scope NZ/US tax, inappropriate, personal-advice, in-scope controls); verify each refusal category is detected and in-scope controls are not falsely refused.

### Tests for User Story 3 (write FIRST)

- [ ] T073 [P] [US3] Unit test — non-English detection at `backend/tests/unit/test_language_detection.py`
- [ ] T074 [P] [US3] Unit test — banned-keyword rule set at `backend/tests/unit/test_banned_keyword_rules.py`
- [ ] T075 [P] [US3] Integration test — out-of-scope (NZ/US tax) refusal with reason `out-of-scope` at `backend/tests/integration/test_us3_out_of_scope_refusal.py`
- [ ] T076 [P] [US3] Integration test — inappropriate-content refusal with reason `inappropriate` at `backend/tests/integration/test_us3_inappropriate_refusal.py`
- [ ] T077 [P] [US3] Integration test — personal-advice refusal with reason `personal-advice` at `backend/tests/integration/test_us3_personal_advice_refusal.py`
- [ ] T078 [P] [US3] Integration test — in-scope general question is NOT falsely refused at `backend/tests/integration/test_us3_in_scope_passthrough.py`

### Implementation for User Story 3

- [ ] T079 [P] [US3] Implement the language detector wrapper at `backend/src/agents/input_guard/language_detector.py` (`langdetect`-backed, deterministic seed)
- [ ] T080 [P] [US3] Implement the deterministic rules layer at `backend/src/agents/input_guard/deterministic_rules.py` — non-English short-circuit + banned-keyword rule set + obvious-illegal patterns
- [ ] T081 [P] [US3] Implement the dedicated boundary classifier at `backend/src/agents/input_guard/boundary_classifier.py` — Claude Haiku 4.5 with a constrained JSON output schema `{ verdict, confidence }`; records `node_invocation` row
- [ ] T082 [P] [US3] Author and version the classifier system prompt + schema at `backend/src/agents/input_guard/boundary_classifier_prompt.py` (constant + `BOUNDARY_CLASSIFIER_VERSION`)
- [ ] T083 [US3] Implement the scope-safety guard node at `backend/src/agents/input_guard/scope_safety_node.py` composing rules layer first then classifier; sets `scope_verdict` and routes to refusal for any non-`in_scope` verdict
- [ ] T084 [US3] Wire `pii_node` → `scope_safety_node` order in `backend/src/agents/graph.py` and add the refusal-routing edges for each

**Checkpoint**: User Story 3 in place; FR-010a fully satisfied.

---

## Phase 6: User Story 4 — Crawl → Leaf-URL Inventory (Priority: P2)

**Goal**: Produce a reviewable inventory of leaf-level `www.ato.gov.au` URLs from configured seeds, respecting `robots.txt` and a polite rate limit.

**Independent Test**: Run the crawler against a single ATO section with a small depth cap; verify the inventory file passes the JSON-Schema in `contracts/url-inventory.schema.json` and contains the expected leaf URLs vs a hand-curated reference list.

### Tests for User Story 4 (write FIRST)

- [ ] T085 [P] [US4] Unit test — URL normalization (lowercase scheme/host, strip fragment, sort query params) at `backend/tests/unit/test_url_normalizer.py`
- [ ] T086 [P] [US4] Unit test — leaf classifier (text-length threshold + URL-pattern blacklist) at `backend/tests/unit/test_leaf_classifier.py`
- [ ] T087 [P] [US4] Unit test — robots.txt disallow handling at `backend/tests/unit/test_robots_wrapper.py`
- [ ] T088 [P] [US4] Unit test — token-bucket rate limiter respects QPS at `backend/tests/unit/test_rate_limiter.py`
- [ ] T089 [P] [US4] Integration test — small slice crawl produces inventory that validates against `contracts/url-inventory.schema.json` at `backend/tests/integration/test_us4_crawl_inventory_schema.py`
- [ ] T090 [P] [US4] Integration test — depth cap respected; pages beyond depth are not visited at `backend/tests/integration/test_us4_depth_cap.py`

### Implementation for User Story 4

- [ ] T091 [P] [US4] Implement URL normalizer at `backend/src/ingestion/crawler/url_normalizer.py`
- [ ] T092 [P] [US4] Implement protego-based robots.txt wrapper at `backend/src/ingestion/crawler/robots.py`
- [ ] T093 [P] [US4] Implement token-bucket rate limiter at `backend/src/ingestion/crawler/rate_limiter.py`
- [ ] T094 [P] [US4] Implement leaf classifier at `backend/src/ingestion/crawler/leaf_classifier.py`
- [ ] T095 [US4] Implement the async BFS crawler at `backend/src/ingestion/crawler/crawl.py` using `httpx.AsyncClient` with the above utilities; emits per-URL `url_inventory` rows and a `crawl_run` summary
- [ ] T096 [US4] Implement the crawler CLI entrypoint at `backend/src/ingestion/crawler/__main__.py` accepting `--seed`, `--depth`, `--rate-limit`, `--output`; writes a JSON file conforming to `contracts/url-inventory.schema.json` and validates the output in-process before exit
- [ ] T097 [P] [US4] Document crawler usage in `backend/README.md` and link from `quickstart.md`

**Checkpoint**: User Story 4 in place; inventory artifact available for the scraper.

---

## Phase 7: User Story 5 — Scrape and Index ATO Content (Priority: P2)

**Goal**: Given a URL inventory, fetch each page, extract main content, chunk, embed, and write to the retrieval index with full provenance.

**Independent Test**: Run scraper against a 50-URL slice; verify each chunk traceable to a source URL, re-scrape after a fixture content change produces superseded chunks, retrieval returns a chunk by content keyword.

### Tests for User Story 5 (write FIRST)

- [ ] T098 [P] [US5] Unit test — trafilatura main-content extraction on saved ATO HTML fixtures at `backend/tests/unit/test_main_content_extraction.py`
- [ ] T099 [P] [US5] Unit test — token-aware chunker (boundary preference, target token count, overlap) at `backend/tests/unit/test_chunker.py`
- [ ] T100 [P] [US5] Unit test — content-hash dedup at `backend/tests/unit/test_content_hash_dedup.py`
- [ ] T101 [P] [US5] Integration test — scrape a small inventory slice and verify chunks present in DB with provenance fields populated at `backend/tests/integration/test_us5_scrape_index.py`
- [ ] T102 [P] [US5] Integration test — re-scrape with changed content supersedes prior chunks at `backend/tests/integration/test_us5_supersede_on_change.py`
- [ ] T103 [P] [US5] Integration test — chunk provenance lookup by `chunk_id` returns source URL, fetch timestamp, content hash, source last-modified at `backend/tests/integration/test_us5_chunk_provenance.py`

### Implementation for User Story 5

- [ ] T104 [P] [US5] Implement HTTP fetcher with conditional GETs (`If-Modified-Since`) at `backend/src/ingestion/scraper/fetcher.py`
- [ ] T105 [P] [US5] Implement main-content extractor wrapper at `backend/src/ingestion/scraper/extractor.py` (trafilatura with sane defaults + selectolax fallback)
- [ ] T106 [P] [US5] Implement token-aware chunker at `backend/src/ingestion/scraper/chunker.py` (~500 tokens, ~80 overlap, paragraph-boundary preference)
- [ ] T107 [P] [US5] Implement batched embedder caller at `backend/src/ingestion/scraper/batch_embedder.py` reusing T038
- [ ] T108 [US5] Implement the scraper orchestrator at `backend/src/ingestion/scraper/scrape.py` consuming a validated inventory, writing `source_document` and `chunk` rows with provenance, applying supersede logic on content-hash change
- [ ] T109 [US5] Implement the scraper CLI at `backend/src/ingestion/scraper/__main__.py` accepting `--inventory` and `--limit`; validates the inventory against the schema before processing
- [ ] T110 [US5] Replace the seed corpus from US1 with the scraped corpus in development: document the swap path in `quickstart.md`

**Checkpoint**: User Story 5 in place; the assistant runs against the real ATO corpus.

---

## Phase 8: User Story 6 — Golden Evaluation Set and Harness (Priority: P2)

**Goal**: Produce a 30-question golden set with expected outcomes (answer + expected citations OR refusal + expected reason) and a harness that runs it against the chat API, scoring citation correctness, refusal correctness, and groundedness — and exits non-zero when thresholds are missed.

**Independent Test**: Run the harness against the US1 build; confirm per-question verdicts for all 30 questions and aggregate metrics. Hand-verify five randomly selected verdicts.

### Tests for User Story 6 (write FIRST)

- [ ] T111 [P] [US6] Unit test — `golden_set.yaml` schema validation: exactly 30 entries, required fields present, expected_outcome consistent with refusal/citation fields at `backend/tests/unit/test_golden_set_schema.py`
- [ ] T112 [P] [US6] Unit test — citation-correctness scorer at `backend/tests/unit/test_citation_correctness_scorer.py`
- [ ] T113 [P] [US6] Unit test — refusal-correctness scorer at `backend/tests/unit/test_refusal_correctness_scorer.py`
- [ ] T114 [P] [US6] Unit test — groundedness scorer (BM25 over chunk text) at `backend/tests/unit/test_groundedness_scorer.py`
- [ ] T115 [P] [US6] Integration test — harness run produces report with per-question verdicts and aggregate metrics at `backend/tests/integration/test_us6_harness_report.py`
- [ ] T116 [P] [US6] Integration test — harness exits non-zero when any configured threshold is missed at `backend/tests/integration/test_us6_harness_exit_code.py`

### Implementation for User Story 6

- [ ] T117 [US6] Author the 30-question golden set at `backend/data/golden_set.yaml` covering GST, income tax brackets, tax-free threshold, deductions, BAS, PAYG, and refusal cases (out-of-scope, PII-integral, personal-advice); include `expected_citation_urls` for answer cases and `expected_refusal_reason` for refusal cases (FR-023)
- [ ] T118 [US6] Have a second engineering-team reader review the golden set per the spec Assumptions section, record `reviewed_by` in the YAML
- [ ] T119 [P] [US6] Implement the YAML loader + validator at `backend/src/eval/golden_set.py` (mirrors `eval_question` schema; loads into the `eval_question` table for join-able reporting)
- [ ] T120 [P] [US6] Implement the citation-correctness scorer at `backend/src/eval/scorers/citation_correctness.py`
- [ ] T121 [P] [US6] Implement the refusal-correctness scorer at `backend/src/eval/scorers/refusal_correctness.py`
- [ ] T122 [P] [US6] Implement the groundedness scorer at `backend/src/eval/scorers/groundedness.py` (BM25 over chunk text supporting each factual sentence)
- [ ] T123 [US6] Implement the harness runner at `backend/src/eval/harness.py` — loads golden set, calls `POST /chat` for each question, runs scorers, records `eval_run` and `eval_result` rows
- [ ] T124 [P] [US6] Implement the aggregate report writer at `backend/src/eval/report.py` — emits JSON + HTML report under `reports/eval-<run-id>/`
- [ ] T125 [US6] Implement the harness CLI at `backend/src/eval/__main__.py` accepting `--golden-set` and `--report-dir`; threshold configuration drives exit code
- [ ] T126 [US6] Add the harness as a CI job in `.github/workflows/ci.yml` that triggers on changes to `backend/src/agents/**`, `backend/src/ingestion/**`, `backend/data/golden_set.yaml`, or `frontend/src/lib/chatClient.ts`

**Checkpoint**: User Story 6 in place; release gate ready per Principle II.

---

## Phase 9: User Story 7 — Confidence and Correctness Grading (Priority: P3)

**Goal**: Surface a confidence-and-correctness badge per answer; refuse rather than render any answer below threshold; persist numeric scores in the audit log.

**Independent Test**: Run a mix of well-covered, thin-support, and stale-source questions; verify the badge appears on every answer, numeric scores in `audit_record`, and below-threshold answers are refused rather than rendered.

### Tests for User Story 7 (write FIRST)

- [ ] T127 [P] [US7] Unit test — confidence composite scorer at `backend/tests/unit/test_confidence_scorer.py`
- [ ] T128 [P] [US7] Unit test — correctness composite scorer at `backend/tests/unit/test_correctness_scorer.py`
- [ ] T129 [P] [US7] Unit test — band bucketing (High/Medium/Low) at `backend/tests/unit/test_confidence_band.py`
- [ ] T130 [P] [US7] Integration test — below-threshold answer triggers `low-confidence` refusal at `backend/tests/integration/test_us7_low_confidence_refusal.py`
- [ ] T131 [P] [US7] Frontend unit test — `ConfidenceBadge` renders next to answer at `frontend/tests/unit/ConfidenceBadge.test.tsx`
- [ ] T132 [P] [US7] Frontend e2e — badge visible on a successful answer at `frontend/tests/e2e/us7_confidence_badge.spec.ts`

### Implementation for User Story 7

- [ ] T133 [P] [US7] Implement confidence scorer at `backend/src/agents/scoring/confidence.py` (`α · max(similarity) + (1-α) · finished_naturally`)
- [ ] T134 [P] [US7] Implement correctness scorer at `backend/src/agents/scoring/correctness.py` (BM25 per factual-sentence match)
- [ ] T135 [P] [US7] Implement band-bucketing utility at `backend/src/agents/scoring/banding.py`
- [ ] T136 [US7] Implement the scoring node at `backend/src/agents/scoring/scoring_node.py` — composes confidence + correctness, applies thresholds, routes to refusal with reason `low-confidence` when below threshold; persists numeric scores in `answer.confidence_score`, `answer.correctness_score`, and `answer.confidence_band`
- [ ] T137 [US7] Wire the scoring node between `citation_check` and `finalize` in `backend/src/agents/graph.py`
- [ ] T138 [P] [US7] Implement `frontend/src/components/ConfidenceBadge.tsx` rendering the High/Medium/Low badge with appropriate ARIA label and color contrast
- [ ] T139 [US7] Update `frontend/src/components/ChatPanel.tsx` to render the badge alongside answers

**Checkpoint**: All user stories independently functional.

---

## Phase 10: Polish and Cross-Cutting Concerns

**Purpose**: Improvements that span user stories and prepare the v1 internal preview.

- [ ] T140 [P] WCAG 2.2 AA audit job at `.github/workflows/ci.yml` using `@axe-core/playwright` against every primary route; zero AA violations is a release gate (SC-011)
- [ ] T141 [P] Add an OpenAPI drift check to CI that compares the live FastAPI schema against `contracts/api-chat.openapi.yaml` and fails the build on divergence
- [ ] T142 [P] Add a CI check that asserts `len(golden_set.yaml) == 30` (FR-023)
- [ ] T143 [P] Backend documentation refresh at `backend/README.md` (env vars, run commands, deployment notes for Railway Singapore)
- [ ] T144 [P] Frontend documentation refresh at `frontend/README.md` (Vercel deployment, env vars, accessibility checks)
- [ ] T145 [P] Add the LangSmith project configuration per env (`ato-assistant-dev`, `ato-assistant-eval`, `ato-assistant-preview`) and document the redaction policy at `docs/observability.md`
- [ ] T146 Run `quickstart.md` end-to-end on a clean checkout and fix any drift; record findings in the PR description
- [ ] T147 [P] Manual screen-reader smoke-test checklist at `docs/accessibility-screen-reader-checklist.md` (VoiceOver + NVDA scenarios for the chat happy path, refusal flow, predominant disclaimer, per-answer disclaimer, badge)
- [ ] T148 Performance baseline: capture P50 and P95 turn latency on the preview deploy under single-user load and record in `docs/performance-baseline.md`; flag any breach of SC-008 (P50 ≤ 5 s, P95 ≤ 10 s) before merge

---

## Dependencies and Execution Order

### Phase dependencies

- **Setup (Phase 1)**: no dependencies — start immediately
- **Foundational (Phase 2)**: depends on Setup; BLOCKS all user stories
- **US1 (Phase 3)**: depends on Foundational
- **US2 (Phase 4)**: depends on Foundational; can run in parallel with US1 if staffed (writes its own modules under `agents/input_guard/`)
- **US3 (Phase 5)**: depends on Foundational; can run in parallel with US1/US2 (writes its own modules; touches `graph.py` last)
- **US4 (Phase 6)**: depends on Foundational; fully independent of US1-US3
- **US5 (Phase 7)**: depends on Foundational; reuses the embedder built in US1 (T038); should follow US4 to consume real inventories but a hand-curated inventory may substitute
- **US6 (Phase 8)**: depends on US1 being callable (Phase 3 complete); runs against the chat API
- **US7 (Phase 9)**: depends on US1 (chat path), US5 (real corpus for stable scoring), US6 (threshold tuning)
- **Polish (Phase 10)**: depends on all desired user stories being complete

### User-story-completion order (suggested)

1. **MVP**: US1 (P1) — demo-ready cited-answer / refusal flow over the seed corpus
2. **Trust gates**: US2 + US3 (P2) — input guardrails before any wider exposure
3. **Real corpus**: US4 → US5 (P2) — sequential within ingestion
4. **Quality gate**: US6 (P2) — enables CI regression on retrieval/generation/citation changes
5. **Grading UX**: US7 (P3) — user-visible quality signal
6. **Polish + release prep**: Phase 10

### Within each user story (mandatory)

- Tests are written and observed to FAIL before any implementation task in that story (Principle II)
- Models / DB writes before services
- Services before nodes / API routes
- Backend before frontend within a story
- Story complete (all acceptance scenarios pass) before moving to the next priority

### Parallel opportunities

- All Setup tasks marked `[P]` can run in parallel (T002 / T003 / T004 / T005 / T006 / T007 / T008)
- Foundational `[P]` tasks T014–T022 can run in parallel after T013
- Per-story: all `[P]` test tasks can be authored in parallel; per-story implementation `[P]` tasks can run in parallel where they touch separate files
- US1 frontend tasks (T049–T053) and backend tasks (T040–T048) split cleanly across developers
- US4 utility modules (T091–T094) can be built in parallel

---

## Parallel Example: User Story 1 tests

```bash
# Authoring tests in parallel before any T036+ implementation:
Task: T025 Contract test for POST /chat answer shape
Task: T026 Contract test for POST /chat refusal shape
Task: T027 Contract test for GET /system-info
Task: T028 Integration test - cited-answer flow over seed corpus
Task: T029 Integration test - refusal when no source covers the query
Task: T030 Integration test - citation-misalignment refusal
Task: T031 Integration test - citation source_url domain filter
Task: T032 Frontend unit test - PredominantDisclaimer
Task: T033 Frontend unit test - PerAnswerDisclaimer
Task: T034 Frontend e2e - cited-answer happy path
Task: T035 Frontend e2e - refusal card
```

---

## Implementation Strategy

### MVP first (User Story 1 only)

1. Complete Phase 1 (Setup)
2. Complete Phase 2 (Foundational — CRITICAL, blocks all stories)
3. Complete Phase 3 (User Story 1) end-to-end against the seed corpus
4. **STOP and VALIDATE**: run the US1 acceptance scenarios manually and via the contract + integration tests
5. Demo internally; this is the MVP cut

### Incremental delivery

1. Setup + Foundational → foundation ready
2. Add US1 → test independently → MVP demo
3. Add US2 (PII) and US3 (scope/safety) → test independently → safe-for-internal-exposure preview
4. Add US4 (crawl) → produce real inventory artifact
5. Add US5 (scrape) → swap seed corpus for real ATO corpus
6. Add US6 (golden eval) → enable CI regression gate
7. Add US7 (grading) → user-visible quality badge
8. Polish (Phase 10) → release prep for internal preview launch

### Parallel team strategy

With multiple developers, after Phase 2 completes:

- Developer A: US1 (MVP)
- Developer B: US4 → US5 (ingestion)
- Developer C: US2 (PII) and US3 (scope/safety) (closely related modules under `input_guard/`)
- Developer D (or A after US1): US6 (golden eval set + harness)

---

## Notes

- `[P]` tasks = different files, no dependencies on incomplete tasks in this phase
- `[Story]` label maps tasks to a specific user story for traceability
- Each user story is independently completable and testable
- Verify tests fail before implementing (Principle II)
- Commit after each task or logical group
- Stop at any checkpoint to validate the story independently
- Avoid: vague tasks, same-file conflicts, cross-story dependencies that break independence
