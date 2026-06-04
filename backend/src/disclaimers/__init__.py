"""Disclaimer templates for the ATO Assistant (T021).

Re-exports the two user-facing disclaimer strings and the version
constant so callers can import from :mod:`disclaimers` directly without
having to know the module layout.
"""

from __future__ import annotations

from .templates import DISCLAIMER_VERSION, PER_ANSWER, PREDOMINANT

__all__ = ["DISCLAIMER_VERSION", "PER_ANSWER", "PREDOMINANT"]
