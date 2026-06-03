-- =====================================================================
-- Project:   ATO Assistant (ato-assistant-opus-spdd)
-- Migration: 0001_initial_schema.sql
-- Date:      2026-06-03
-- Feature:   001-ato-chat-rag (Phase 2: Foundational)
-- Tasks:     T010, T011, T012 (see specs/001-ato-chat-rag/tasks.md)
--
-- T010 finding (Voyage AI default embedding dimension):
--   The Voyage AI ``voyage-3-large`` model returns embeddings of
--   dimension **1024** by default. Matryoshka-supported alternative
--   dimensions are 256, 512, 1024, 2048; the default (1024) is used
--   when the API caller does not pass ``output_dimension``. This
--   schema fixes ``chunk.embedding`` to ``VECTOR(1024)`` accordingly.
--
-- Schema note (US7 deferral):
--   ``answer.confidence_score``, ``answer.correctness_score``, and
--   ``answer.confidence_band`` are NULLABLE in this v1 schema because
--   User Story 1 (MVP, Phase 3) writes ``answer`` rows before User
--   Story 7 (Phase 9) implements the scoring node. US7 carries a
--   follow-up migration that backfills existing rows and tightens
--   these columns to NOT NULL. See data-model.md for the full
--   rationale.
--
-- Authoritative entity definitions: specs/001-ato-chat-rag/data-model.md
-- =====================================================================

-- ---------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- gen_random_uuid()


-- ---------------------------------------------------------------------
-- source_document
-- ---------------------------------------------------------------------

CREATE TABLE source_document (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_url            TEXT        NOT NULL,
    fetched_at            TIMESTAMPTZ NOT NULL,
    source_last_modified  TIMESTAMPTZ NULL,
    content_hash          BYTEA       NOT NULL,
    main_text             TEXT        NOT NULL,
    http_status           INTEGER     NOT NULL,
    extraction_warnings   JSONB       NOT NULL DEFAULT '[]'::jsonb,
    is_superseded         BOOLEAN     NOT NULL DEFAULT false,
    superseded_at         TIMESTAMPTZ NULL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Only one active (non-superseded) snapshot per URL.
CREATE UNIQUE INDEX source_document_active_url_uidx
    ON source_document (source_url)
    WHERE is_superseded = false;

CREATE INDEX source_document_content_hash_idx
    ON source_document (content_hash);


-- ---------------------------------------------------------------------
-- chunk
-- ---------------------------------------------------------------------

CREATE TABLE chunk (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_document_id  UUID         NOT NULL
        REFERENCES source_document (id) ON DELETE CASCADE,
    chunk_index         INTEGER      NOT NULL,
    text                TEXT         NOT NULL,
    token_count         INTEGER      NOT NULL,
    embedding           VECTOR(1024) NOT NULL,
    is_superseded       BOOLEAN      NOT NULL DEFAULT false,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX chunk_source_document_chunk_index_uidx
    ON chunk (source_document_id, chunk_index);

-- HNSW index for approximate nearest-neighbour cosine search over the
-- voyage-3-large embedding space.
CREATE INDEX chunk_embedding_hnsw_idx
    ON chunk
    USING hnsw (embedding vector_cosine_ops);


-- ---------------------------------------------------------------------
-- crawl_run  (declared before url_inventory due to FK dependency)
-- ---------------------------------------------------------------------

CREATE TABLE crawl_run (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at               TIMESTAMPTZ NOT NULL,
    finished_at              TIMESTAMPTZ NULL,
    seed_urls                TEXT[]      NOT NULL,
    depth_cap                INTEGER     NOT NULL,
    rate_limit_qps           NUMERIC     NOT NULL,
    pages_visited            INTEGER     NOT NULL DEFAULT 0,
    pages_skipped_by_robots  INTEGER     NOT NULL DEFAULT 0,
    pages_failed             INTEGER     NOT NULL DEFAULT 0
);


-- ---------------------------------------------------------------------
-- url_inventory
-- ---------------------------------------------------------------------

CREATE TABLE url_inventory (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url                    TEXT        NOT NULL UNIQUE,
    discovered_at          TIMESTAMPTZ NOT NULL,
    crawl_run_id           UUID        NOT NULL
        REFERENCES crawl_run (id),
    crawl_depth            INTEGER     NOT NULL,
    http_status            INTEGER     NULL,
    is_leaf                BOOLEAN     NOT NULL,
    is_robots_disallowed   BOOLEAN     NOT NULL DEFAULT false,
    user_agent             TEXT        NOT NULL
);


-- ---------------------------------------------------------------------
-- query
-- ---------------------------------------------------------------------

CREATE TABLE query (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id            UUID        NOT NULL,
    received_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    masked_text           TEXT        NOT NULL,
    pii_detected          TEXT[]      NOT NULL DEFAULT '{}',
    pii_outcome           TEXT        NOT NULL
        CHECK (pii_outcome IN ('clean', 'masked', 'refused')),
    pii_scanner_version   TEXT        NOT NULL,
    language_detected     TEXT        NULL
);


-- ---------------------------------------------------------------------
-- retrieval
-- ---------------------------------------------------------------------

CREATE TABLE retrieval (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_id                  UUID         NOT NULL
        REFERENCES query (id) ON DELETE CASCADE,
    top_k                     INTEGER      NOT NULL,
    chunk_ids                 UUID[]       NOT NULL,
    similarities              NUMERIC[]    NOT NULL,
    embedding_model_version   TEXT         NOT NULL,
    created_at                TIMESTAMPTZ  NOT NULL DEFAULT now()
);


-- ---------------------------------------------------------------------
-- answer
--
-- NOTE: confidence_score, correctness_score, and confidence_band are
-- NULLABLE in v1; US7 ships a follow-up migration to backfill and
-- tighten them to NOT NULL.
-- ---------------------------------------------------------------------

CREATE TABLE answer (
    id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_id                        UUID        NOT NULL
        REFERENCES query (id) ON DELETE CASCADE,
    retrieval_id                    UUID        NOT NULL
        REFERENCES retrieval (id),
    text                            TEXT        NOT NULL,
    confidence_score                NUMERIC     NULL,
    correctness_score               NUMERIC     NULL,
    confidence_band                 TEXT        NULL
        CHECK (confidence_band IS NULL
               OR confidence_band IN ('high', 'medium', 'low')),
    model_identity                  TEXT        NOT NULL,
    model_version                   TEXT        NOT NULL,
    generation_params               JSONB       NOT NULL,
    per_answer_disclaimer_version   TEXT        NOT NULL,
    generated_at                    TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ---------------------------------------------------------------------
-- citation
-- ---------------------------------------------------------------------

CREATE TABLE citation (
    id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    answer_id                       UUID        NOT NULL
        REFERENCES answer (id) ON DELETE CASCADE,
    chunk_id                        UUID        NOT NULL
        REFERENCES chunk (id),
    source_url                      TEXT        NOT NULL,
    anchor                          TEXT        NULL,
    snippet                         TEXT        NOT NULL,
    source_last_modified_at_cite    TIMESTAMPTZ NULL,
    liveness_status                 TEXT        NOT NULL
        CHECK (liveness_status IN ('live', 'unknown', 'stale')),
    liveness_checked_at             TIMESTAMPTZ NULL
);


-- ---------------------------------------------------------------------
-- refusal
-- ---------------------------------------------------------------------

CREATE TABLE refusal (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_id            UUID        NOT NULL
        REFERENCES query (id) ON DELETE CASCADE,
    reason_code         TEXT        NOT NULL
        CHECK (reason_code IN (
            'no-source',
            'low-confidence',
            'citation-misalignment',
            'stale-source',
            'pii-integral',
            'pii-scanner-fail',
            'out-of-scope',
            'inappropriate',
            'personal-advice',
            'non-english'
        )),
    user_message        TEXT        NOT NULL,
    refused_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    produced_by_node    TEXT        NOT NULL
        CHECK (produced_by_node IN (
            'pii_node',
            'scope_safety_node',
            'retrieval_node',
            'generation_node',
            'citation_check_node',
            'scoring_node'
        ))
);


-- ---------------------------------------------------------------------
-- node_invocation
--
-- Per-node model invocation log. Joined to ``query`` so an auditor can
-- reconstruct which model produced which intermediate decision for a
-- given turn. Deterministic-only nodes MAY skip the row, or write a
-- row with NULL model fields for timing-only capture.
-- ---------------------------------------------------------------------

CREATE TABLE node_invocation (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_id            UUID        NOT NULL
        REFERENCES query (id) ON DELETE CASCADE,
    node_name           TEXT        NOT NULL
        CHECK (node_name IN (
            'pii_node',
            'pii_intent_classifier',
            'scope_safety_node',
            'boundary_classifier',
            'retrieval_node',
            'generation_node',
            'citation_check_node',
            'scoring_node',
            'finalize_node'
        )),
    model_identity      TEXT        NULL,
    model_version       TEXT        NULL,
    processing_region   TEXT        NULL,
    started_at          TIMESTAMPTZ NOT NULL,
    finished_at         TIMESTAMPTZ NOT NULL,
    input_token_count   INTEGER     NULL,
    output_token_count  INTEGER     NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX node_invocation_query_id_idx
    ON node_invocation (query_id);


-- ---------------------------------------------------------------------
-- audit_record
-- ---------------------------------------------------------------------

CREATE TABLE audit_record (
    id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_id                        UUID        NOT NULL
        REFERENCES query (id) ON DELETE CASCADE,
    answer_id                       UUID        NULL
        REFERENCES answer (id),
    refusal_id                      UUID        NULL
        REFERENCES refusal (id),
    retrieval_id                    UUID        NULL
        REFERENCES retrieval (id),
    langsmith_trace_id              TEXT        NULL,
    processing_region_llm           TEXT        NOT NULL,
    processing_region_embedding     TEXT        NOT NULL,
    processing_region_observability TEXT        NOT NULL,
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Exactly one of (answer_id, refusal_id) must be set.
    CHECK ((answer_id IS NULL) <> (refusal_id IS NULL))
);


-- ---------------------------------------------------------------------
-- eval_question
-- ---------------------------------------------------------------------

CREATE TABLE eval_question (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question_text               TEXT        NOT NULL,
    expected_outcome            TEXT        NOT NULL
        CHECK (expected_outcome IN ('answer', 'refusal')),
    expected_refusal_reason     TEXT        NULL,
    expected_citation_urls      TEXT[]      NOT NULL DEFAULT '{}',
    topic                       TEXT        NOT NULL
        CHECK (topic IN (
            'gst',
            'income-tax',
            'tax-free-threshold',
            'deductions',
            'bas',
            'payg',
            'refusal',
            'other'
        )),
    difficulty                  TEXT        NOT NULL
        CHECK (difficulty IN ('easy', 'medium', 'hard')),
    author                      TEXT        NOT NULL,
    reviewed_by                 TEXT        NULL,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ---------------------------------------------------------------------
-- eval_run
-- ---------------------------------------------------------------------

CREATE TABLE eval_run (
    id                                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    commit_sha                         TEXT        NOT NULL,
    started_at                         TIMESTAMPTZ NOT NULL,
    finished_at                        TIMESTAMPTZ NULL,
    harness_version                    TEXT        NOT NULL,
    corpus_index_version               TEXT        NOT NULL,
    aggregate_citation_correctness     NUMERIC     NULL,
    aggregate_refusal_correctness      NUMERIC     NULL,
    aggregate_groundedness             NUMERIC     NULL,
    exit_status                        TEXT        NOT NULL
        CHECK (exit_status IN ('pass', 'fail', 'partial'))
);


-- ---------------------------------------------------------------------
-- eval_result
-- ---------------------------------------------------------------------

CREATE TABLE eval_result (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    eval_run_id              UUID    NOT NULL
        REFERENCES eval_run (id) ON DELETE CASCADE,
    eval_question_id         UUID    NOT NULL
        REFERENCES eval_question (id),
    actual_outcome           TEXT    NOT NULL
        CHECK (actual_outcome IN ('answer', 'refusal')),
    actual_text              TEXT    NOT NULL,
    actual_citation_urls     TEXT[]  NOT NULL DEFAULT '{}',
    verdict                  TEXT    NOT NULL
        CHECK (verdict IN (
            'pass',
            'fail',
            'refused_correct',
            'refused_incorrect'
        )),
    citation_correctness     NUMERIC NULL,
    groundedness             NUMERIC NULL,
    notes                    TEXT    NULL
);

-- =====================================================================
-- End of migration 0001_initial_schema.sql
-- =====================================================================
