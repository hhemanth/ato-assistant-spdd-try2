# Data Model: ATO Chat with Cited Answers and RAG Pipeline

**Phase 1 output** — maps each entity in `spec.md` to a concrete
Postgres schema in Supabase (Sydney). All tables live in the `public`
schema unless noted. Vector columns use `pgvector`. UUIDs are produced
with `gen_random_uuid()`. Timestamps are `TIMESTAMPTZ` in UTC.

> Authoritative DDL lives at `backend/src/db/schema.sql`; this document
> is the human-readable contract that drives it.

## Conventions

- Every table has `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`
  unless otherwise specified, and `created_at TIMESTAMPTZ NOT NULL
  DEFAULT now()`.
- Soft-supersede pattern: tables with versioned content carry an
  `is_superseded BOOLEAN NOT NULL DEFAULT false` and a
  `superseded_at TIMESTAMPTZ` populated on supersede.
- Enums are stored as `TEXT` with a `CHECK` constraint listing allowed
  values. This avoids migration churn when new values are added.
- Plaintext PII is never stored. Where a column might appear to allow
  it (e.g., `query.original_text`), the column is in fact populated
  with the *post-mask* text or the redaction token — see `query` below.

## Tables

### `source_document`

A single fetched `www.ato.gov.au` page snapshot. Entity per spec.md.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | — |
| `source_url` | TEXT NOT NULL | Normalized URL (lowercase scheme/host, no fragment, sorted query params). |
| `fetched_at` | TIMESTAMPTZ NOT NULL | When the scraper fetched the page. |
| `source_last_modified` | TIMESTAMPTZ NULL | From the page's `Last-Modified` header. |
| `content_hash` | BYTEA NOT NULL | SHA-256 of extracted main text. |
| `main_text` | TEXT NOT NULL | Extracted by trafilatura. |
| `http_status` | INTEGER NOT NULL | Capture for audit. |
| `extraction_warnings` | JSONB NOT NULL DEFAULT '[]' | Any extraction issues. |
| `is_superseded` | BOOLEAN NOT NULL DEFAULT false | Marked true when a newer snapshot supersedes. |
| `superseded_at` | TIMESTAMPTZ NULL | Set when `is_superseded` flips. |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | — |

**Indexes**: `(source_url, is_superseded) WHERE is_superseded = false`
(unique partial index — only one active snapshot per URL);
`(content_hash)`.

**Lifecycle**: created on scrape success → may be superseded by a later
scrape with a different `content_hash`.

### `chunk`

A retrievable unit derived from a `source_document`.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | — |
| `source_document_id` | UUID NOT NULL REFERENCES `source_document(id)` ON DELETE CASCADE | — |
| `chunk_index` | INTEGER NOT NULL | Position within the source document. |
| `text` | TEXT NOT NULL | The chunk content. |
| `token_count` | INTEGER NOT NULL | For budget enforcement. |
| `embedding` | VECTOR(1024) NOT NULL | Voyage `voyage-3-large` dim. |
| `is_superseded` | BOOLEAN NOT NULL DEFAULT false | Mirrors source supersede. |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | — |

**Indexes**: `(source_document_id, chunk_index)` unique;
HNSW on `embedding` with `vector_cosine_ops`.

**Retrieval filter**: queries hard-restrict to
`is_superseded = false`.

### `url_inventory`

Crawler output (User Story 4). Each row is a discovered URL.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | — |
| `url` | TEXT NOT NULL UNIQUE | Normalized. |
| `discovered_at` | TIMESTAMPTZ NOT NULL | — |
| `crawl_run_id` | UUID NOT NULL REFERENCES `crawl_run(id)` | Which run produced this row. |
| `crawl_depth` | INTEGER NOT NULL | Depth from the seed. |
| `http_status` | INTEGER NULL | NULL until first probe. |
| `is_leaf` | BOOLEAN NOT NULL | Classifier verdict. |
| `is_robots_disallowed` | BOOLEAN NOT NULL DEFAULT false | Logged but skipped. |
| `user_agent` | TEXT NOT NULL | The exact UA string used. |

### `crawl_run`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | — |
| `started_at` | TIMESTAMPTZ NOT NULL | — |
| `finished_at` | TIMESTAMPTZ NULL | — |
| `seed_urls` | TEXT[] NOT NULL | Inputs to the run. |
| `depth_cap` | INTEGER NOT NULL | — |
| `rate_limit_qps` | NUMERIC NOT NULL | — |
| `pages_visited` | INTEGER NOT NULL DEFAULT 0 | — |
| `pages_skipped_by_robots` | INTEGER NOT NULL DEFAULT 0 | — |
| `pages_failed` | INTEGER NOT NULL DEFAULT 0 | — |

### `query`

One row per user-submitted turn (after PII handling).

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | — |
| `session_id` | UUID NOT NULL | Server-generated; not linked to an identity. |
| `received_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | — |
| `masked_text` | TEXT NOT NULL | Post-PII-masking text — the only form stored. |
| `pii_detected` | TEXT[] NOT NULL DEFAULT '{}' | Detected PII classes (no plaintext). |
| `pii_outcome` | TEXT NOT NULL CHECK (`pii_outcome` IN ('clean','masked','refused')) | — |
| `pii_scanner_version` | TEXT NOT NULL | For audit. |
| `language_detected` | TEXT NULL | e.g., `en`, `zh`. |

**Invariant**: if any entry exists in `pii_detected`, `masked_text`
MUST NOT contain the underlying plaintext. Enforced by the PII guard
module's tests (FR-009).

### `retrieval`

The retrieval result for one `query`.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | — |
| `query_id` | UUID NOT NULL REFERENCES `query(id)` ON DELETE CASCADE | — |
| `top_k` | INTEGER NOT NULL | Cutoff applied. |
| `chunk_ids` | UUID[] NOT NULL | Ranked. Same length as `similarities`. |
| `similarities` | NUMERIC[] NOT NULL | Cosine similarities. |
| `embedding_model_version` | TEXT NOT NULL | e.g., `voyage-3-large@2026-04-XX`. |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | — |

### `answer`

A successful (non-refusal) generation. Refusals go to `refusal`.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | — |
| `query_id` | UUID NOT NULL REFERENCES `query(id)` ON DELETE CASCADE | — |
| `retrieval_id` | UUID NOT NULL REFERENCES `retrieval(id)` | — |
| `text` | TEXT NOT NULL | The rendered answer. |
| `confidence_score` | NUMERIC NULL | 0..1 per scoring node. NULLABLE in v1 schema because US1 (MVP) writes `answer` rows before US7 (P3) implements scoring; US7 includes a migration that backfills existing rows and flips the column to NOT NULL. |
| `correctness_score` | NUMERIC NULL | 0..1 per scoring node. Nullable for the same reason as `confidence_score`; tightened to NOT NULL by US7's migration. |
| `confidence_band` | TEXT NULL CHECK (`confidence_band` IS NULL OR `confidence_band` IN ('high','medium','low')) | User-facing badge bucket. Nullable for the same reason; tightened to NOT NULL by US7's migration. |
| `model_identity` | TEXT NOT NULL | e.g., `claude-sonnet-4-6`. |
| `model_version` | TEXT NOT NULL | Anthropic version pin. |
| `generation_params` | JSONB NOT NULL | Temperature, max-tokens, top-p, system prompt id. |
| `per_answer_disclaimer_version` | TEXT NOT NULL | Reference to disclaimer template. |
| `generated_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | — |

### `citation`

A pointer from an answer to a chunk.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | — |
| `answer_id` | UUID NOT NULL REFERENCES `answer(id)` ON DELETE CASCADE | — |
| `chunk_id` | UUID NOT NULL REFERENCES `chunk(id)` | — |
| `source_url` | TEXT NOT NULL | Denormalized for audit stability after re-scrape. |
| `anchor` | TEXT NULL | URL fragment when available. |
| `snippet` | TEXT NOT NULL | Snippet shown to the user. |
| `source_last_modified_at_cite` | TIMESTAMPTZ NULL | Source freshness at cite-time (FR-006). |
| `liveness_status` | TEXT NOT NULL CHECK (`liveness_status` IN ('live','unknown','stale')) | From the citation-check node. |
| `liveness_checked_at` | TIMESTAMPTZ NULL | — |

### `refusal`

A non-answer response.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | — |
| `query_id` | UUID NOT NULL REFERENCES `query(id)` ON DELETE CASCADE | — |
| `reason_code` | TEXT NOT NULL CHECK (`reason_code` IN ('no-source','low-confidence','citation-misalignment','stale-source','pii-integral','pii-scanner-fail','out-of-scope','inappropriate','personal-advice','non-english')) | — |
| `user_message` | TEXT NOT NULL | The text shown to the user. |
| `refused_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | — |
| `produced_by_node` | TEXT NOT NULL CHECK (`produced_by_node` IN ('pii_node','scope_safety_node','retrieval_node','generation_node','citation_check_node','scoring_node')) | — |

### `node_invocation`

Per-node invocation record for any LangGraph node that calls a model.
Captures model identity, version, region, and timing so Principle V's
transparency posture extends to every model call — not just the
answer-generating one. Joined to `query` so an auditor can reconstruct
which model produced which intermediate decision for a given turn.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | — |
| `query_id` | UUID NOT NULL REFERENCES `query(id)` ON DELETE CASCADE | — |
| `node_name` | TEXT NOT NULL CHECK (`node_name` IN ('pii_node','pii_intent_classifier','scope_safety_node','boundary_classifier','retrieval_node','generation_node','citation_check_node','scoring_node','finalize_node')) | Which LangGraph node performed the invocation. |
| `model_identity` | TEXT NULL | e.g., `claude-sonnet-4-6`, `claude-haiku-4-5`, `voyage-3-large`. NULL when the node ran entirely deterministically (no model call). |
| `model_version` | TEXT NULL | Provider-pinned version. NULL when no model call. |
| `processing_region` | TEXT NULL | e.g., `us-east-1`. NULL when no model call. |
| `started_at` | TIMESTAMPTZ NOT NULL | — |
| `finished_at` | TIMESTAMPTZ NOT NULL | — |
| `input_token_count` | INTEGER NULL | When provider reports it. |
| `output_token_count` | INTEGER NULL | When provider reports it. |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | — |

**Indexes**: `(query_id)`.

**Write pattern**: every node that calls a model writes one row at
node exit; deterministic-only nodes MAY skip the row, or write a row
with NULL model fields if they want timing capture.

### `audit_record`

One row per user-facing turn (FR-017). Joins query, retrieval, answer
or refusal, plus orchestration metadata.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | — |
| `query_id` | UUID NOT NULL REFERENCES `query(id)` ON DELETE CASCADE | — |
| `answer_id` | UUID NULL REFERENCES `answer(id)` | Set when answered. |
| `refusal_id` | UUID NULL REFERENCES `refusal(id)` | Set when refused. |
| `retrieval_id` | UUID NULL REFERENCES `retrieval(id)` | — |
| `langsmith_trace_id` | TEXT NULL | For cross-reference. |
| `processing_region_llm` | TEXT NOT NULL | e.g., `us-east-1`. |
| `processing_region_embedding` | TEXT NOT NULL | — |
| `processing_region_observability` | TEXT NOT NULL | — |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | — |

**Constraint**: exactly one of `answer_id`, `refusal_id` is non-NULL
(checked via `CHECK ((answer_id IS NULL) <> (refusal_id IS NULL))`).

### `eval_question`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | Stable per question; referenced by the YAML manifest. |
| `question_text` | TEXT NOT NULL | — |
| `expected_outcome` | TEXT NOT NULL CHECK (`expected_outcome` IN ('answer','refusal')) | — |
| `expected_refusal_reason` | TEXT NULL | Required when `expected_outcome = 'refusal'`. |
| `expected_citation_urls` | TEXT[] NOT NULL DEFAULT '{}' | Required (non-empty) when `expected_outcome = 'answer'`. |
| `topic` | TEXT NOT NULL CHECK (`topic` IN ('gst','income-tax','tax-free-threshold','deductions','bas','payg','refusal','other')) | Domain tag. |
| `difficulty` | TEXT NOT NULL CHECK (`difficulty` IN ('easy','medium','hard')) | — |
| `author` | TEXT NOT NULL | Engineering team author + reviewer. |
| `reviewed_by` | TEXT NULL | Second reader. |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | — |

> Source of truth is `backend/data/golden_set.yaml`; this table is
> populated by `eval/load_golden_set.py` for reporting joins.

### `eval_run` / `eval_result`

`eval_run`:

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | — |
| `commit_sha` | TEXT NOT NULL | — |
| `started_at` | TIMESTAMPTZ NOT NULL | — |
| `finished_at` | TIMESTAMPTZ NULL | — |
| `harness_version` | TEXT NOT NULL | — |
| `corpus_index_version` | TEXT NOT NULL | — |
| `aggregate_citation_correctness` | NUMERIC NULL | — |
| `aggregate_refusal_correctness` | NUMERIC NULL | — |
| `aggregate_groundedness` | NUMERIC NULL | — |
| `exit_status` | TEXT NOT NULL CHECK (`exit_status` IN ('pass','fail','partial')) | CI gate. |

`eval_result`:

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | — |
| `eval_run_id` | UUID NOT NULL REFERENCES `eval_run(id)` ON DELETE CASCADE | — |
| `eval_question_id` | UUID NOT NULL REFERENCES `eval_question(id)` | — |
| `actual_outcome` | TEXT NOT NULL CHECK (`actual_outcome` IN ('answer','refusal')) | — |
| `actual_text` | TEXT NOT NULL | — |
| `actual_citation_urls` | TEXT[] NOT NULL DEFAULT '{}' | — |
| `verdict` | TEXT NOT NULL CHECK (`verdict` IN ('pass','fail','refused_correct','refused_incorrect')) | — |
| `citation_correctness` | NUMERIC NULL | — |
| `groundedness` | NUMERIC NULL | — |
| `notes` | TEXT NULL | — |

## Entity-to-spec mapping

| Spec entity | Tables |
|---|---|
| Query | `query` |
| Source Document | `source_document` |
| Chunk | `chunk` |
| Retrieval | `retrieval` |
| Answer | `answer` |
| Citation | `citation` |
| Refusal | `refusal` |
| PII Detection Result | embedded in `query` (`pii_detected`, `pii_outcome`, `pii_scanner_version`) |
| URL Inventory Entry | `url_inventory` + `crawl_run` |
| Eval Question | `eval_question` (mirror of `golden_set.yaml`) |
| Eval Result | `eval_result` + `eval_run` |
| Audit Record | `audit_record` |
| (Transparency support) Per-node model invocation log | `node_invocation` |

## Validation rules summary

- **FR-001 / FR-013**: every `answer` row MUST have ≥ 1 `citation` row
  whose `chunk_id` belongs to the chunks listed in the referenced
  `retrieval.chunk_ids`. Enforced at the citation-check node and
  asserted by integration tests.
- **FR-008 / FR-009**: `query.masked_text` MUST NOT contain plaintext of
  the entities listed in `query.pii_detected`. Enforced by the PII
  guard's redaction step and asserted by unit tests + integration tests
  using a fixed PII corpus.
- **FR-018a (relaxed)**: `audit_record.processing_region_*` columns are
  non-NULL — region disclosure to auditors is preserved even when
  cross-border processing is permitted.
- **FR-022**: re-scrape with a different `content_hash` → previous
  `source_document` row's `is_superseded` flips true and a new row is
  inserted; previous `chunk` rows are bulk-marked
  `is_superseded = true`.
- **FR-023**: `eval_question` count = 30. Enforced by a CI check on
  `golden_set.yaml`.
