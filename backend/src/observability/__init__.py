"""Observability glue for the ATO Assistant.

This package owns the LangSmith client configuration and the trace-
redaction wrapper (T020) that guarantees no plaintext PII reaches the
LangSmith service. The redactor is the LangSmith-side companion to the
PII-safe logger in :mod:`audit.pii_safe_logger` -- both layers refuse
to emit anything that hasn't already been masked, in line with FR-009.
"""
