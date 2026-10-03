/**
 * AUD-027 smoke: open review -> the PDF page is actually drawn -> each item's highlight lands on
 * its value text -> Export to Excel produces a real .xlsx download.
 *
 * Runs on the PyMuPDF-parsed seed job. The same highlight check on the Docling job is added with
 * AUD-002 (batch 3), where it is the red test for the mirrored-bbox bug.
 */
import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { canvasInkPixels, centreInside, highlightInPageSpace, manifest, openReview, viewerOutcome } from './helpers'

test('review smoke: render, highlight on value, export', async ({ page }, testInfo) => {
  const job = manifest().pymupdf
  await openReview(page, job.filename)
  expect(await viewerOutcome(page)).toBe('rendered')
  expect(await canvasInkPixels(page)).toBeGreaterThan(2000)

  await page.getByRole('tab', { name: /^All/ }).click()
  const misses: string[] = []
  for (const [itemId, valueRect] of Object.entries(job.expected_value_rects)) {
    await page.locator(`[data-item-id="${itemId}"]`).click()
    await page.waitForTimeout(400)
    const box = await highlightInPageSpace(page)
    if (!box || !centreInside(valueRect, box)) misses.push(`${itemId}: value=${valueRect.map(Math.round)} highlight=${box?.map(Math.round)}`)
  }
  expect(misses).toEqual([])

  const generated = page.waitForResponse((r) => r.url().includes(`/models/${job.job_id}/generate`) && r.request().method() === 'POST')
  await page.getByRole('button', { name: 'Export to Excel' }).click()
  expect((await generated).status()).toBe(200)

  await page.getByRole('button', { name: 'Export options' }).click()
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('link', { name: /Download \.xlsx/ }).click(),
  ])
  const path = testInfo.outputPath('export.xlsx')
  await download.saveAs(path)
  expect(readFileSync(path).subarray(0, 2).toString('latin1')).toBe('PK')
})
