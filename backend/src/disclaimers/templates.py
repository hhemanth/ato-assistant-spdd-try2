"""Versioned disclaimer templates (T021).

Two strings are exported:

* :data:`PREDOMINANT` — the app-level disclaimer shown at session
  entry (FR-002) including the APP 8 cross-border processing notice
  (FR-018a).
* :data:`PER_ANSWER` — the short notice attached to every rendered
  answer (FR-003).

Both are bound to :data:`DISCLAIMER_VERSION`. Bump the version any
time the wording changes — the audit log and golden-set fixtures
reference the version so changes are reviewable and regression-testable.
"""

from __future__ import annotations

from typing import Final

DISCLAIMER_VERSION: Final[str] = "2026-06-03-001"
"""Disclaimer wording version. Bump (date + sequence) on any edit to
:data:`PREDOMINANT` or :data:`PER_ANSWER` so the audit log can pin
exact wording per turn."""


PREDOMINANT: Final[str] = (
    "The ATO Assistant helps you find factual answers to Australian tax "
    "questions sourced from ato.gov.au.\n"
    "\n"
    "This assistant does not provide personal financial, legal, or tax "
    "advice. Answers are limited to factual statements supported by cited "
    "ATO content and may not reflect your individual circumstances.\n"
    "\n"
    "Some processing of your queries occurs outside Australia. Do not "
    "enter sensitive personal information (such as your tax file number, "
    "date of birth, or residential address) into this assistant. This "
    "notice is provided in line with Australian Privacy Principle 8 "
    "(cross-border disclosure of personal information).\n"
    "\n"
    "For personalised advice, consult a registered tax agent or contact "
    "the ATO directly (https://www.ato.gov.au/about-ato/contact-us)."
)
"""App-level predominant disclaimer (FR-002 + FR-018a).

Ordered: (1) scope-and-purpose; (2) not-personal-advice; (3) APP 8
cross-border notice; (4) where to get personalised advice. Suitable
for embedding in a UI banner above the chat input."""


PER_ANSWER: Final[str] = (
    "This information is sourced from ato.gov.au and is not personal "
    "advice — consult a registered tax agent for advice on your "
    "specific situation."
)
"""Per-answer disclaimer (FR-003). Verbatim wording from T021 — keep
the em-dash as ``\\u2014`` so the source bytes are unambiguous."""


__all__ = ["DISCLAIMER_VERSION", "PER_ANSWER", "PREDOMINANT"]
