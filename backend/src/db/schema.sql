-- =====================================================================
-- Project:   ATO Assistant (ato-assistant-opus-spdd)
-- File:      backend/src/db/schema.sql
-- Date:      2026-06-03
-- Feature:   001-ato-chat-rag (Phase 2: Foundational, Task T013)
--
-- Purpose
-- -------
-- One-shot apply script for **local development only**. Concatenates
-- every migration under ``backend/src/db/migrations/`` in lexicographic
-- order via psql's ``\ir`` (include-relative) meta-command. The result
-- is a single end-to-end schema apply:
--
--     psql "$SUPABASE_DB_URL" -f backend/src/db/schema.sql
--
-- Production environments MUST apply migrations individually (one
-- ``0001_*.sql`` at a time, with version tracking) rather than via
-- this aggregator. This file exists purely for fast local bootstrap
-- and for the seed-corpus loader's test fixtures.
--
-- When a new migration is added (``0002_*.sql``, ``0003_*.sql``, ...),
-- append a corresponding ``\ir migrations/0002_*.sql`` line below in
-- order.
-- =====================================================================

\echo 'Applying migration 0001_initial_schema.sql ...'
\ir migrations/0001_initial_schema.sql
\echo 'Done: 0001_initial_schema.sql'
