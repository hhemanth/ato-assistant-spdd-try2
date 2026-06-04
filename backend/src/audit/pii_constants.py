"""Canonical PII class identifiers shared by the audit and observability layers.

The redaction token format ``<REDACTED:{pii_class}>`` is the single source of
truth for what may appear in any audit log, persisted column, or tracing
payload after PII handling. T019 (the PII-safe logger) and T020 (the
LangSmith trace redactor) MUST import :data:`PII_CLASSES` and
:data:`REDACTION_TOKEN_REGEX` from this module so that any future addition
to the recognised set (TFN / ABN / ACN recognisers land in T066-T068)
flows to both writers automatically.

The set of canonical class names is normative for FR-007, FR-008, and
FR-009: see ``specs/001-ato-chat-rag/spec.md`` Functional Requirements.
The mapping :data:`PRESIDIO_ENTITY_TO_PII_CLASS` translates the names
emitted by Presidio's built-in recognisers (``EMAIL_ADDRESS``,
``PHONE_NUMBER``, ``DATE_TIME``, ``PERSON``, ``LOCATION``) and the future
custom recognisers (``AU_TFN``, ``AU_ABN``, ``AU_ACN``) into the
canonical set. Anything Presidio detects that is NOT in this mapping is
still treated as a guard failure -- silently dropping unknown entity
types would weaken FR-009.
"""

from __future__ import annotations

import re
from typing import Final

# --- Canonical class names ---------------------------------------------------

PII_CLASS_PERSON: Final[str] = "PERSON"
PII_CLASS_EMAIL: Final[str] = "EMAIL"
PII_CLASS_PHONE: Final[str] = "PHONE"
PII_CLASS_DOB: Final[str] = "DOB"
PII_CLASS_LOCATION: Final[str] = "LOCATION"
PII_CLASS_TFN: Final[str] = "TFN"
PII_CLASS_ABN: Final[str] = "ABN"
PII_CLASS_ACN: Final[str] = "ACN"

#: The closed set of canonical PII class names. Used by:
#:
#: * :mod:`audit.pii_safe_logger` -- the guard whitelist of allowed redaction
#:   tokens.
#: * :mod:`observability.langsmith_redactor` -- the substitute-with-token
#:   policy on state fields.
#: * The eventual PII guard module (T070) that enforces FR-009's invariant
#:   on persisted columns.
PII_CLASSES: Final[frozenset[str]] = frozenset(
    {
        PII_CLASS_PERSON,
        PII_CLASS_EMAIL,
        PII_CLASS_PHONE,
        PII_CLASS_DOB,
        PII_CLASS_LOCATION,
        PII_CLASS_TFN,
        PII_CLASS_ABN,
        PII_CLASS_ACN,
    }
)

#: Presidio's built-in recognisers do not use our canonical names; the
#: custom recognisers landing in T066-T068 will. Add new mappings as new
#: recognisers come online. Mapping keys are the ``entity_type`` strings
#: that Presidio emits.
PRESIDIO_ENTITY_TO_PII_CLASS: Final[dict[str, str]] = {
    "PERSON": PII_CLASS_PERSON,
    "EMAIL_ADDRESS": PII_CLASS_EMAIL,
    "PHONE_NUMBER": PII_CLASS_PHONE,
    "DATE_TIME": PII_CLASS_DOB,
    "LOCATION": PII_CLASS_LOCATION,
    # Custom Australian recognisers (registered by T066-T068).
    "AU_TFN": PII_CLASS_TFN,
    "AU_ABN": PII_CLASS_ABN,
    "AU_ACN": PII_CLASS_ACN,
}


# --- Redaction token ---------------------------------------------------------


def redaction_token(pii_class: str) -> str:
    """Build the canonical redaction token for ``pii_class``.

    Raises :class:`ValueError` for any class outside :data:`PII_CLASSES` so
    that callers cannot fabricate a token that the guard would later
    silently accept.
    """

    if pii_class not in PII_CLASSES:
        raise ValueError(f"Unknown PII class: {pii_class!r}")
    return f"<REDACTED:{pii_class}>"


def redaction_token_for_classes(pii_classes: list[str]) -> str:
    """Build a stable redaction token for one or more classes.

    When a single value contains multiple PII classes (e.g. a string with
    both a name and a TFN) the redactor emits a token whose payload is the
    sorted classes joined by ``+``. This keeps the token format
    deterministic for audit comparison and for the guard's safe-list
    regex.

    The empty input produces a generic ``<REDACTED:PII>`` token only as a
    last resort -- in practice the caller always knows at least one class.
    """

    if not pii_classes:
        # No specific class -- fall back to a generic marker. This is
        # accepted by the safe-list regex below but should be rare.
        return "<REDACTED:PII>"
    unique_sorted = sorted({c for c in pii_classes if c in PII_CLASSES})
    if not unique_sorted:
        return "<REDACTED:PII>"
    return f"<REDACTED:{'+'.join(unique_sorted)}>"


#: Regex matching any well-formed redaction token. Used to strip allowed
#: tokens from a string before running the Presidio guard (any residue
#: that still trips Presidio is the leak we want to surface).
#:
#: The payload character class accepts the canonical class names plus
#: ``+`` for joined-class tokens and ``PII`` for the generic fallback.
REDACTION_TOKEN_REGEX: Final[re.Pattern[str]] = re.compile(r"<REDACTED:[A-Z][A-Z0-9+]*>")


__all__ = [
    "PII_CLASSES",
    "PII_CLASS_ABN",
    "PII_CLASS_ACN",
    "PII_CLASS_DOB",
    "PII_CLASS_EMAIL",
    "PII_CLASS_LOCATION",
    "PII_CLASS_PERSON",
    "PII_CLASS_PHONE",
    "PII_CLASS_TFN",
    "PRESIDIO_ENTITY_TO_PII_CLASS",
    "REDACTION_TOKEN_REGEX",
    "redaction_token",
    "redaction_token_for_classes",
]
