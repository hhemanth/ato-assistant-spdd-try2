/**
 * T050 [US1] PredominantDisclaimer — app-level disclaimer (FR-002 + FR-018a).
 *
 * Server component (static content, no client interactivity). Rendered once
 * at session entry above the chat surface. Wording is duplicated verbatim
 * from `backend/src/disclaimers/templates.py::PREDOMINANT` so that the
 * frontend banner stays in lockstep with the audit-logged version. If the
 * backend `DISCLAIMER_VERSION` bumps, this file MUST be updated in the same
 * change set.
 *
 * Accessibility:
 * - `role="note"` marks the region as non-interactive informational.
 * - `aria-label` provides a discoverable name to assistive tech.
 * - Tailwind colour pair (amber-50 / amber-900 in light, amber-950 /
 *   amber-100 in dark) is a known WCAG AA contrast combo.
 */

export function PredominantDisclaimer(): React.ReactElement {
  return (
    <aside
      role="note"
      aria-label="Important information about this assistant"
      className="border border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100 rounded-md p-4 my-4"
    >
      <h2 className="font-semibold text-base mb-2">
        Before you start
      </h2>
      <p className="text-sm leading-relaxed">
        ATO Assistant answers Australian tax questions using only published
        content from ato.gov.au.
      </p>
      <p className="text-sm leading-relaxed mt-2">
        This is not personal advice. Answers are limited to factual
        statements supported by cited ATO content and may not reflect your
        individual circumstances.
      </p>
      <p className="text-sm leading-relaxed mt-2">
        Some processing of your queries occurs outside Australia. Do not
        enter sensitive personal information (such as your tax file number,
        date of birth, or residential address). This notice is provided in
        line with Australian Privacy Principle 8 (cross-border disclosure
        of personal information).
      </p>
      <p className="text-sm leading-relaxed mt-2">
        For advice specific to your situation, consult a registered tax
        agent or contact the ATO directly.
      </p>
    </aside>
  );
}

export default PredominantDisclaimer;
