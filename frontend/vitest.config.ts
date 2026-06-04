/**
 * Vitest configuration for the ATO Assistant frontend unit tests.
 *
 * Notes:
 * - `jsdom` is required for @testing-library/react to mount components.
 * - `setupFiles` registers `@testing-library/jest-dom/vitest` so the
 *   `toHaveTextContent`-style matchers work in expect().
 * - `resolve.alias["@"]` mirrors the tsconfig `paths` mapping so that
 *   tests can import from `@/components/...` (which is also what the
 *   product code uses). Without this alias, the failure mode for the
 *   not-yet-existing `<PredominantDisclaimer />` would be "alias
 *   unresolved" instead of the intended "component not implemented".
 */

import { defineConfig } from 'vitest/config';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['tests/unit/**/*.test.{ts,tsx}'],
    setupFiles: ['./tests/unit/setup.ts'],
  },
  resolve: {
    alias: {
      '@': resolve(here, 'src'),
    },
  },
});
