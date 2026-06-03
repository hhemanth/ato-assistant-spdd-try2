"""Audit-side modules for the ATO Assistant.

This package owns the write-path for FR-017 (per-turn audit records),
FR-018a (processing-region columns), and the per-node invocation log
that surfaces every model call in the LangGraph pipeline. Loggers that
must never emit pre-mask PII live here too (T019).
"""
