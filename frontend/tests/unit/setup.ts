/**
 * Vitest unit-test bootstrap.
 *
 * Registers @testing-library/jest-dom matchers (e.g. toBeInTheDocument,
 * toHaveTextContent) onto Vitest's expect. Imported by every test in
 * `tests/unit/**` via the `setupFiles` entry in `vitest.config.ts`.
 */

import '@testing-library/jest-dom/vitest';
