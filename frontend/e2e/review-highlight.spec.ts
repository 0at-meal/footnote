/**
 * AUD-002 / FN-003: in the real review UI, every item's highlight must contain its value text
 * (PyMuPDF text-search oracle from the seed manifest), for Docling-parsed and PyMuPDF-parsed jobs.
 */
import { test, expect, type Page } from '@playwright/test'
import { centreInside, highlightInPageSpace, manifest, openReview, viewerOutcome, type E2EJob } from './helpers'

async function highlightMisses(page: Page, job: E2EJob): Promise<string[]> {
  await page.getByRole('tab', { name: /^All/ }).click()
  const misses: string[] = []
  for (const [itemId, valueRect] of Object.entries(job.expected_value_rects)) {
    await page.locator(`[data-item-id="${itemId}"]`).click()
    await page.waitForTimeout(400)
    const box = await highlightInPageSpace(page)
    if (!box || !centreInside(valueRect, box)) {
      misses.push(`${itemId}: value=${valueRect.map(Math.round)} highlight=${box?.map(Math.round)}`)
    }
  }
  return misses
}

for (const parser of ['docling', 'pymupdf'] as const) {
  test(`highlights land on their values (${parser} job)`, async ({ page }) => {
    const job = manifest()[parser]
    await openReview(page, job.filename)
    expect(await viewerOutcome(page)).toBe('rendered')
    expect(await highlightMisses(page, job)).toEqual([])
  })
}
