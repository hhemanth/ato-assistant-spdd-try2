"""Database access package for the ATO Assistant backend.

The package wraps the Supabase Postgres + ``pgvector`` store:

* :mod:`db.repos` — typed SQLAlchemy 2.x repositories per entity
  (the modules created by tasks.md task T014).

DDL (``schema.sql``) and migrations live alongside this package.
"""
