"""LangSmith trace-redaction wrapper -- the trace-side guard for FR-009.

LangSmith traces inherit every value the LangGraph state carries through
a run. That includes ``original_text`` -- the pre-mask user prompt --
which would leak plaintext PII to a third-party observability service
if forwarded verbatim. This module is the single mediator between the
agent state and the LangSmith ``Client``.

Contract (mirrors the documented hooks in the installed ``langsmith``
SDK, v0.8.x):

* :meth:`LangSmithRedactor.redact_state` -- consumes the agent's
  :class:`dict`-shaped state and returns a deep-copied view where
  ``original_text`` is replaced by a canonical redaction token whenever
  ``pii_outcome`` is ``masked`` or ``refused``. The ``clean`` case may
  pass through unchanged.
* :meth:`LangSmithRedactor.redact_payload` -- a recursive walker that
  applies the same :class:`PIISafeLogger` guard to every string leaf in
  an arbitrary trace payload (``inputs`` / ``outputs`` / ``metadata``).
  Strings that trip the Presidio guard are substituted with the
  canonical token; strings that contain only safe-listed
  ``<REDACTED:CLASS>`` markers pass through.

The :func:`install_langsmith_redactor` helper returns a configured
LangSmith :class:`~langsmith.Client` wired to the redactor via the
documented ``hide_inputs`` / ``hide_outputs`` / ``hide_metadata`` hooks
(present in ``langsmith>=0.8.0``) and the ``anonymizer`` callable. We
prefer the explicit-hook API over the legacy ``Run`` post-processor
because the hooks are documented, version-stable, and run before the
payload is buffered for upload -- so a leak cannot escape via the
buffer flush on shutdown.

The state shape this module relies on is the documented contract from
``specs/001-ato-chat-rag/data-model.md`` (the ``query`` entity):

* ``pii_outcome``: ``"clean" | "masked" | "refused"``
* ``pii_detected``: ``list[str]`` -- canonical PII class names
* ``original_text``: ``str`` -- the pre-mask user input
* ``masked_text``: ``str`` -- already redacted; safe to pass through

The module does NOT import :mod:`agents.state` -- the agent state
TypedDict lands in a parallel task -- so all access is via
:meth:`dict.get`.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any, Final

from audit.pii_constants import (
    PRESIDIO_ENTITY_TO_PII_CLASS,
    REDACTION_TOKEN_REGEX,
    redaction_token_for_classes,
)
from audit.pii_safe_logger import (
    PIIRedactionGuardError,
    PIISafeLogger,
)

if TYPE_CHECKING:
    from presidio_analyzer import AnalyzerEngine

#: State key whose value is the pre-mask user prompt. Centralised so the
#: integration test in T065 can monkeypatch it if the agent state evolves.
ORIGINAL_TEXT_KEY: Final[str] = "original_text"
PII_OUTCOME_KEY: Final[str] = "pii_outcome"
PII_DETECTED_KEY: Final[str] = "pii_detected"

#: Outcomes that REQUIRE redaction of ``original_text`` before tracing.
#: ``clean`` passes through; ``masked`` and ``refused`` MUST be replaced.
_OUTCOMES_REQUIRING_REDACTION: Final[frozenset[str]] = frozenset({"masked", "refused"})


class LangSmithRedactor:
    """Redact agent state and trace payloads before LangSmith upload.

    A single instance is reusable across many runs. The underlying
    :class:`PIISafeLogger` lazily initialises the Presidio analyzer on
    first use, so constructing the redactor at import time is cheap.
    """

    def __init__(
        self,
        *,
        logger: PIISafeLogger | None = None,
        analyzer: AnalyzerEngine | None = None,
    ) -> None:
        # The logger is reused only for its Presidio guard. We never
        # call ``info``/``error`` on it from here -- guard hits are
        # turned into in-place substitutions, not log lines, because
        # the redactor runs on every trace event and logging would
        # amplify any noisy false positive.
        self._guard_logger = logger or PIISafeLogger(
            name="ato.observability.langsmith_redactor",
            analyzer=analyzer,
        )

    # -- state-level redaction ----------------------------------------

    def redact_state(self, state: dict[str, Any]) -> dict[str, Any]:
        """Return a deep-copied ``state`` with PII fields tokenised.

        When ``state['pii_outcome']`` is ``masked`` or ``refused``, the
        ``original_text`` field is replaced with the canonical
        ``<REDACTED:...>`` token built from ``state['pii_detected']``.
        The ``clean`` case is allowed through unchanged because the PII
        scanner has explicitly classified the text as PII-free.

        All other string leaves in the state are passed through
        :meth:`redact_payload` so a stray plaintext that bypassed the
        masker (e.g. echoed inside an intermediate node's debug field)
        is still caught.
        """

        redacted = copy.deepcopy(state)
        outcome = redacted.get(PII_OUTCOME_KEY)
        if outcome in _OUTCOMES_REQUIRING_REDACTION:
            detected_raw = redacted.get(PII_DETECTED_KEY) or []
            detected = [c for c in detected_raw if isinstance(c, str)]
            redacted[ORIGINAL_TEXT_KEY] = redaction_token_for_classes(detected)
        # Apply the recursive guard to the remaining payload. The
        # ``original_text`` key (already a safe token if we just
        # rewrote it) passes through cleanly.
        return self._redact_mapping(redacted)

    # -- payload-level redaction --------------------------------------

    def redact_payload(self, obj: Any) -> Any:
        """Recursively replace any plaintext-PII string with a token.

        The walker preserves container shape so LangSmith's run
        renderer continues to display the trace in the expected layout.
        Strings that contain only safe-listed redaction tokens (or no
        PII at all) are returned unchanged.
        """

        if isinstance(obj, str):
            return self._redact_string(obj)
        if isinstance(obj, dict):
            return self._redact_mapping(obj)
        if isinstance(obj, list):
            return [self.redact_payload(v) for v in obj]
        if isinstance(obj, tuple):
            return tuple(self.redact_payload(v) for v in obj)
        if isinstance(obj, set):
            # Sets of strings are common in tag-style metadata; treat
            # each member as an independent leaf.
            return {self.redact_payload(v) for v in obj}
        # Everything else (int, float, bool, None, custom objects)
        # passes through. We do NOT stringify-and-scan unknown objects
        # because doing so could leak the object's ``repr`` to the
        # trace; the caller is responsible for stringifying before
        # handing the value to the trace.
        return obj

    # -- LangSmith hook adapters --------------------------------------

    def hide_inputs(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Adapter for ``langsmith.Client(hide_inputs=...)``."""

        return self._redact_mapping(inputs)

    def hide_outputs(self, outputs: dict[str, Any]) -> dict[str, Any]:
        """Adapter for ``langsmith.Client(hide_outputs=...)``."""

        return self._redact_mapping(outputs)

    def hide_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """Adapter for ``langsmith.Client(hide_metadata=...)``."""

        return self._redact_mapping(metadata)

    def anonymizer(self, data: dict[str, Any]) -> dict[str, Any]:
        """Adapter for ``langsmith.Client(anonymizer=...)``.

        LangSmith's documented anonymizer signature is
        ``Callable[[dict], dict]``; we route it through
        :meth:`_redact_mapping` so the same guard runs whether the SDK
        chooses to call the per-payload hooks or the global anonymizer.
        """

        return self._redact_mapping(data)

    # -- internals -----------------------------------------------------

    def _redact_mapping(self, mapping: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in mapping.items():
            out[key] = self.redact_payload(value)
        return out

    def _redact_string(self, text: str) -> str:
        """Run the guard on ``text``; substitute a token on a hit."""

        if not text:
            return text
        try:
            self._guard_logger._assert_no_plaintext_pii(text, field="trace")
        except PIIRedactionGuardError as exc:
            # Translate the detected Presidio entity types into our
            # canonical class names. Unknown entity types fall back to
            # the generic token; this keeps the redactor robust against
            # newly-registered recognisers that haven't yet been added
            # to ``PRESIDIO_ENTITY_TO_PII_CLASS``.
            classes = [
                PRESIDIO_ENTITY_TO_PII_CLASS[e]
                for e in exc.entity_types
                if e in PRESIDIO_ENTITY_TO_PII_CLASS
            ]
            return redaction_token_for_classes(classes)
        # No guard hit -- but the string may still contain known safe-
        # listed tokens, which is fine. Return unchanged.
        _ = REDACTION_TOKEN_REGEX  # imported to keep the safe-list ref obvious
        return text


# -- installation helper -----------------------------------------------


def install_langsmith_redactor(
    redactor: LangSmithRedactor | None = None,
    **client_kwargs: Any,
) -> Any:
    """Return a LangSmith ``Client`` wired to the trace redactor.

    The installed ``langsmith`` SDK (v0.8.x) exposes four documented
    hooks on :class:`langsmith.Client`:

    * ``hide_inputs``
    * ``hide_outputs``
    * ``hide_metadata``
    * ``anonymizer``

    All four are routed through :class:`LangSmithRedactor` so the same
    guard runs on every payload regardless of which hook the SDK
    invokes for a given run event. Caller-supplied ``client_kwargs``
    (e.g. ``api_key``, ``api_url``) are forwarded to the ``Client``
    constructor unmodified; any of the four hook kwargs in
    ``client_kwargs`` overrides the redactor binding -- that escape
    hatch is intentional for tests.

    Returns the configured :class:`langsmith.Client` instance. We
    return the instance rather than mutate a module-level default
    because LangSmith's tracing is per-client; explicit construction
    keeps test isolation straightforward.
    """

    # Deferred so importing this module does not eagerly construct any
    # langsmith state -- many test paths exercise the redactor without
    # ever calling ``install_langsmith_redactor`` and we don't want
    # langsmith's import-time side effects to leak into those runs.
    from langsmith import Client  # noqa: PLC0415

    redactor = redactor or LangSmithRedactor()
    hook_defaults: dict[str, Any] = {
        "hide_inputs": redactor.hide_inputs,
        "hide_outputs": redactor.hide_outputs,
        "hide_metadata": redactor.hide_metadata,
        "anonymizer": redactor.anonymizer,
    }
    for key, default in hook_defaults.items():
        client_kwargs.setdefault(key, default)
    return Client(**client_kwargs)


__all__ = [
    "LangSmithRedactor",
    "install_langsmith_redactor",
]
