/**
 * Playwright configuration for ATO Assistant end-to-end specs.
 *
 * Local execution requires the Next.js dev server to be running on
 * `http://localhost:3000` (i.e. `cd frontend && npm run dev`) before
 * `npx playwright test` is invoked. The configuration deliberately does
 * NOT spawn the dev server itself — Slice 1's UI is not yet implemented,
 * so the bundled e2e spec is marked `test.fixme(true, ...)` to flag it
 * as a known-pending test rather than a flaky run.
 */

import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
