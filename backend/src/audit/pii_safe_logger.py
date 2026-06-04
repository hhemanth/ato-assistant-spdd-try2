"""PII-safe structured logger -- the guard rail for FR-009.

Every other audit-side and node-side logger MUST go through this facade.
The contract is intentionally narrow:

* The caller is expected to pass **already-redacted** text (either a
  literal :data:`<REDACTED:CLASS>` token from
  :mod:`audit.pii_constants`, or the masked output of the PII scanner).
* Before any bytes leave this module, every string argument -- the
  message and each structured field value -- is run through a Presidio
  scan that *strips known redaction tokens first* and then asserts that
  no plaintext PII spans remain. Any residual hit raises
  :class:`PIIRedactionGuardError`, the log entry is dropped, and the
  programmer is forced to fix the call site.

This is a guard, not a masker. Silent scrubbing would mask the
programmer error and leave the same plaintext in some other code path
that doesn't route through the logger. By raising we surface the leak
before it reaches LangSmith, Postgres, or stdout.

The error message itself MUST NOT contain the offending text -- only
the detected entity types and character offsets. Including the leak in
the exception message would defeat the guard.

Custom Australian recognisers for TFN/ABN/ACN land in T066-T068; once
they are registered with the ``AnalyzerEngine`` returned by
:func:`_default_analyzer`, this module picks them up automatically via
the canonical mapping in :mod:`audit.pii_constants`.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Final

from audit.pii_constants import (
    PRESIDIO_ENTITY_TO_PII_CLASS,
    REDACTION_TOKEN_REGEX,
)

if TYPE_CHECKING:
    # Avoid importing Presidio at module-import time -- spaCy is a heavy
    # dependency and we want test runs that mock the logger to remain
    # cheap. The real import is deferred to ``_default_analyzer``.
    from presidio_analyzer import AnalyzerEngine

#: The Presidio entity types we currently scan for. Mirrors the keys of
#: :data:`PRESIDIO_ENTITY_TO_PII_CLASS`. Extra recognisers (T066-T068)
#: are picked up by adding their entity_type to the mapping; the guard
#: discovers them via :meth:`AnalyzerEngine.get_supported_entities`.
_PRESIDIO_BUILTIN_ENTITIES: Final[tuple[str, ...]] = (
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "DATE_TIME",
    "LOCATION",
)


class PIIRedactionGuardError(RuntimeError):
    """Raised when the PII-safe logger detects plaintext PII in a payload.

    The message intentionally omits the offending text -- callers should
    inspect :attr:`entity_types` and :attr:`offsets` to fix the leak.
    """

    def __init__(
        self,
        *,
        entity_types: list[str],
        offsets: list[tuple[int, int]],
        field: str,
    ) -> None:
        self.entity_types = entity_types
        self.offsets = offsets
        self.field = field
        super().__init__(
            "PII redaction guard tripped: "
            f"field={field!r} entity_types={entity_types} "
            f"offsets={offsets}"
        )


class _JSONFormatter(logging.Formatter):
    """Minimal JSON-line formatter for structured fields.

    Adds the ``fields`` dict (set by :class:`PIISafeLogger` via the
    ``extra`` mechanism) as a top-level key. Falls back to ``repr`` for
    anything that isn't JSON-serialisable so the logger never crashes
    the application on a logging call.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload["fields"] = fields
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=repr, ensure_ascii=False)


def _default_analyzer() -> AnalyzerEngine:
    """Build a default Presidio :class:`AnalyzerEngine` instance.

    Lazy-imported so module import stays cheap. Reuses the analyzer for
    all subsequent calls on a given :class:`PIISafeLogger` instance --
    instantiating Presidio pulls spaCy and is slow.
    """

    # The deferred import is deliberate: Presidio drags spaCy and a
    # model-load step into the import graph, which we want to avoid for
    # any test or module that mocks the analyzer out.
    from presidio_analyzer import AnalyzerEngine  # noqa: PLC0415

    return AnalyzerEngine()


class PIISafeLogger:
    """Logging facade that refuses to emit plaintext PII.

    Use exactly like :class:`logging.Logger` for message + structured
    fields:

    .. code-block:: python

        log = PIISafeLogger("ato.audit.query")
        log.info("query received", session_id=sid, masked_text=masked)

    Each ``info/warning/error/exception/debug/critical`` method runs
    the message and every field value through
    :meth:`_assert_no_plaintext_pii` before the record reaches the
    backing :mod:`logging` handler. A guard hit raises
    :class:`PIIRedactionGuardError` and the record is **not** emitted.
    """

    def __init__(
        self,
        name: str = "ato.pii_safe",
        *,
        analyzer: AnalyzerEngine | None = None,
        score_threshold: float = 0.4,
        backend: logging.Logger | None = None,
    ) -> None:
        self._name = name
        self._score_threshold = score_threshold
        # Analyzer is held per-instance so tests can swap in a fake.
        self._analyzer: AnalyzerEngine | None = analyzer
        if backend is None:
            backend = logging.getLogger(name)
            if not backend.handlers:
                handler = logging.StreamHandler()
                handler.setFormatter(_JSONFormatter())
                backend.addHandler(handler)
                backend.propagate = False
        self._backend = backend

    # -- guard ---------------------------------------------------------

    def _get_analyzer(self) -> AnalyzerEngine:
        if self._analyzer is None:
            self._analyzer = _default_analyzer()
        return self._analyzer

    def _supported_entities(self) -> list[str]:
        """Return the entity types the analyzer can produce.

        Falls back to the built-in set when the analyzer's
        introspection API is unavailable so the guard still does
        something useful in test doubles.
        """

        analyzer = self._get_analyzer()
        getter = getattr(analyzer, "get_supported_entities", None)
        if callable(getter):
            try:
                entities = list(getter())
            except (TypeError, ValueError):
                # Some custom analyzers require a language kwarg; the
                # fallback below is acceptable.
                entities = list(_PRESIDIO_BUILTIN_ENTITIES)
        else:
            entities = list(_PRESIDIO_BUILTIN_ENTITIES)
        # Always include the canonical mapping's keys so newly-registered
        # AU recognisers are scanned even if the test double's
        # introspection lies.
        entities.extend(PRESIDIO_ENTITY_TO_PII_CLASS.keys())
        # Dedupe but preserve a stable order.
        seen: set[str] = set()
        out: list[str] = []
        for e in entities:
            if e not in seen:
                seen.add(e)
                out.append(e)
        return out

    def _assert_no_plaintext_pii(self, text: str, *, field: str) -> None:
        """Raise if ``text`` contains any plaintext PII span.

        Known redaction tokens (``<REDACTED:CLASS>``) are stripped before
        the scan so the safe-listed payload does not trip the guard. The
        analyzer is then run over the residue; any hit raises
        :class:`PIIRedactionGuardError`.
        """

        if not text:
            return
        # Strip the safe-list before scanning. Replacing with whitespace
        # of equal length preserves character offsets reported by
        # Presidio, which keeps the error message useful for debugging.
        residue = REDACTION_TOKEN_REGEX.sub(lambda m: " " * (m.end() - m.start()), text)
        analyzer = self._get_analyzer()
        results = analyzer.analyze(
            text=residue,
            entities=self._supported_entities(),
            language="en",
            score_threshold=self._score_threshold,
        )
        hits = list(results)
        if not hits:
            return
        entity_types = [getattr(r, "entity_type", "?") for r in hits]
        offsets = [(getattr(r, "start", -1), getattr(r, "end", -1)) for r in hits]
        raise PIIRedactionGuardError(
            entity_types=entity_types,
            offsets=offsets,
            field=field,
        )

    def _guard_payload(self, msg: str, fields: dict[str, Any]) -> None:
        """Apply the guard to the message and every field value.

        Non-string field values are coerced via ``repr`` for the scan --
        callers should not be smuggling PII through ``int``/``UUID``
        fields, but the coercion makes accidental leaks visible too.
        """

        self._assert_no_plaintext_pii(msg, field="msg")
        for key, value in fields.items():
            if isinstance(value, str):
                scan = value
            elif isinstance(value, bytes):
                scan = value.decode("utf-8", errors="replace")
            else:
                scan = repr(value)
            self._assert_no_plaintext_pii(scan, field=key)

    # -- backend wiring ------------------------------------------------

    def _emit(
        self,
        level: int,
        msg: str,
        fields: dict[str, Any],
        *,
        exc_info: bool = False,
    ) -> None:
        self._guard_payload(msg, fields)
        # The ``extra`` dict surfaces in ``_JSONFormatter`` via
        # ``record.fields``. Stdlib reserves a small set of attribute
        # names on the record; using a single ``fields`` key avoids
        # collisions with attributes like ``name`` or ``msg``.
        self._backend.log(level, msg, extra={"fields": fields}, exc_info=exc_info)

    # -- public facade -------------------------------------------------

    def debug(self, msg: str, **fields: Any) -> None:
        self._emit(logging.DEBUG, msg, fields)

    def info(self, msg: str, **fields: Any) -> None:
        self._emit(logging.INFO, msg, fields)

    def warning(self, msg: str, **fields: Any) -> None:
        self._emit(logging.WARNING, msg, fields)

    def error(self, msg: str, **fields: Any) -> None:
        self._emit(logging.ERROR, msg, fields)

    def exception(self, msg: str, **fields: Any) -> None:
        self._emit(logging.ERROR, msg, fields, exc_info=True)

    def critical(self, msg: str, **fields: Any) -> None:
        self._emit(logging.CRITICAL, msg, fields)


def get_pii_safe_logger(
    name: str = "ato.pii_safe",
    *,
    analyzer: AnalyzerEngine | None = None,
) -> PIISafeLogger:
    """Convenience accessor mirroring :func:`logging.getLogger`."""

    return PIISafeLogger(name=name, analyzer=analyzer)


__all__ = [
    "PIIRedactionGuardError",
    "PIISafeLogger",
    "get_pii_safe_logger",
]
