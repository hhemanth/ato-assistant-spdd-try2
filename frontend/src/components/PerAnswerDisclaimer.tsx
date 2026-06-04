/**
 * T051 [US1] PerAnswerDisclaimer — rendered beneath every answer (FR-003).
 *
 * Server component (static content). Wording duplicated verbatim from
 * `backend/src/disclaimers/templates.py::PER_ANSWER`. Keep the em-dash as
 * the actual U+2014 character so the rendered string is byte-equivalent
 * to the backend canonical version (the audit log records the version,
 * not the bytes — so visual drift would silently diverge).
 */

export function PerAnswerDisclaimer(): React.ReactElement {
  return (
    <div
      role="note"
      aria-label="Per-answer disclaimer"
      className="text-sm text-zinc-600 dark:text-zinc-400 mt-3 italic"
    >
      <p>
        This information is sourced from ato.gov.au and is not personal
        advice — consult a registered tax agent for advice on your
        specific situation.
      </p>
    </div>
  );
}

export default PerAnswerDisclaimer;
