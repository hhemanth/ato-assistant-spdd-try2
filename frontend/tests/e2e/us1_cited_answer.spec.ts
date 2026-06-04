/**
 * T034 [US1] Frontend e2e — cited-answer happy path.
 *
 * Walks the full Slice 1 UX:
 *   1. The predominant disclaimer is visible BEFORE any input is sent
 *      (FR-002 + Acceptance Scenario 3).
 *   2. The user types a tax question and submits it.
 *   3. The rendered answer carries at least one citation link to
 *      `https://www.ato.gov.au/...` (FR-001) and the per-answer
 *      disclaimer text appears beneath it (FR-003 + Acceptance
 *      Scenario 4).
 *
 * Requires the local stack to be running:
 *   - Backend on http://127.0.0.1:8000 with a populated seed corpus
 *     (run `uv run python -m src.ingestion.seed_corpus_loader` once).
 *   - Frontend dev server on http://localhost:3000.
 * The answer round-trips through real Anthropic + Voyage, so the
 * citation-visibility timeout is generous (20s).
 */

import { test, expect } from '@playwright/test';

test('US1 cited-answer happy path', async ({ page }) => {
  await page.goto('/');

  // Predominant disclaimer must be visible before any input is sent.
  await expect(
    page.getByText(/outside Australia/i, { exact: false }),
  ).toBeVisible();
  await expect(page.getByText(/ato\.gov\.au/i, { exact: false }).first()).toBeVisible();

  // Submit a known-in-scope question.
  await page
    .getByRole('textbox', { name: /question|ask|message/i })
    .fill('What is the tax-free threshold in Australia?');
  await page.getByRole('button', { name: /send|submit|ask/i }).click();

  // Answer + citation link to ato.gov.au. The link's visible text is
  // the URL path (host dropped for brevity) and the title is the full
  // URL; the most direct selector is by href pattern.
  const citationLink = page
    .locator('a[href^="https://www.ato.gov.au/"]')
    .first();
  await expect(citationLink).toBeVisible({ timeout: 20_000 });
  await expect(citationLink).toHaveAttribute(
    'href',
    /^https:\/\/www\.ato\.gov\.au\//,
  );

  // Per-answer disclaimer appears beneath every answer.
  await expect(
    page.getByText(/sourced from ato\.gov\.au/i, { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByText(/registered tax agent/i, { exact: false }).first(),
  ).toBeVisible();
});
