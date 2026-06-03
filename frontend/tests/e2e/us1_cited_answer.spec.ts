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
 * Status: `test.fixme(true, ...)` — Slice 1 backend and frontend tasks
 * (T036-T056) are still pending, so running this spec for real would
 * always fail. `fixme` marks the test as known-pending so CI surfaces
 * it without going red until the stack is wired.
 */

import { test, expect } from '@playwright/test';

test('US1 cited-answer happy path', async ({ page }) => {
  test.fixme(true, 'Implementation pending — Slice 1 backend + frontend tasks');

  await page.goto('/');

  // Predominant disclaimer must be visible before any input is sent.
  await expect(
    page.getByText(/outside Australia/i, { exact: false }),
  ).toBeVisible();
  await expect(page.getByText(/ato\.gov\.au/i, { exact: false })).toBeVisible();

  // Submit a known-in-scope question.
  await page
    .getByRole('textbox', { name: /question|ask|message/i })
    .fill('What is the tax-free threshold in Australia?');
  await page.getByRole('button', { name: /send|submit|ask/i }).click();

  // Answer + citation link to ato.gov.au.
  const citationLink = page
    .getByRole('link', { name: /ato\.gov\.au/i })
    .first();
  await expect(citationLink).toBeVisible();
  await expect(citationLink).toHaveAttribute(
    'href',
    /^https:\/\/www\.ato\.gov\.au\//,
  );

  // Per-answer disclaimer appears beneath every answer.
  await expect(
    page.getByText(/sourced from ato\.gov\.au/i, { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByText(/registered tax agent/i, { exact: false }),
  ).toBeVisible();
});
