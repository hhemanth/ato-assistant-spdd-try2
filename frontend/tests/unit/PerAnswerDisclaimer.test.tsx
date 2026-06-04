/**
 * T033 [US1] Frontend unit test — <PerAnswerDisclaimer />.
 *
 * Asserts the verbatim per-answer disclaimer wording mandated by FR-003.
 * Two substring checks: "sourced from ato.gov.au" + "registered tax
 * agent" — these match the canonical wording in
 * `backend/src/disclaimers/templates.py::PER_ANSWER`.
 *
 * Expected current failure: the component file does not yet exist;
 * vite/vitest will fail to resolve `@/components/PerAnswerDisclaimer`.
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { PerAnswerDisclaimer } from '@/components/PerAnswerDisclaimer';

describe('PerAnswerDisclaimer', () => {
  it('renders the canonical FR-003 per-answer disclaimer text', () => {
    render(<PerAnswerDisclaimer />);

    const region =
      screen.queryByRole('note') ??
      screen.queryByRole('region') ??
      document.body;

    expect(region).toHaveTextContent(/sourced from ato\.gov\.au/i);
    expect(region).toHaveTextContent(/registered tax agent/i);
  });
});
