/**
 * T032 [US1] Frontend unit test — <PredominantDisclaimer />.
 *
 * Asserts that the predominant disclaimer component (FR-002 + FR-018a)
 * renders the three mandatory hooks:
 *   1. "ato.gov.au" — scope-and-purpose;
 *   2. "tax agent" — directs the user to professional advice;
 *   3. "outside Australia" — APP 8 cross-border notice.
 *
 * Expected current failure: the component does not yet exist
 * (`@/components/PredominantDisclaimer` resolves to a missing file in
 * `frontend/src/components/`). The expected error is a vite/vitest module
 * resolution error — exactly the right TDD signal for T050 to fix.
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { PredominantDisclaimer } from '@/components/PredominantDisclaimer';

describe('PredominantDisclaimer', () => {
  it('renders the APP 8 cross-border disclaimer text at session entry', () => {
    render(<PredominantDisclaimer />);

    // The disclaimer is expected to live in a landmark — banner OR note
    // both signal "non-interactive informational region" to assistive tech.
    const region =
      screen.queryByRole('banner') ??
      screen.queryByRole('note') ??
      screen.queryByRole('region') ??
      // Fallback to the document body so the substring assertions still
      // fail with a meaningful message if no landmark role is used.
      document.body;

    expect(region).toBeTruthy();
    expect(region).toHaveTextContent(/ato\.gov\.au/i);
    expect(region).toHaveTextContent(/tax agent/i);
    expect(region).toHaveTextContent(/outside Australia/i);
  });
});
