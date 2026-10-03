/**
 * AUD-002 / FN-003: in the real review UI, every item's highlight must contain its value text
 * (PyMuPDF text-search oracle from the seed manifest), for Docling-parsed and PyMuPDF-parsed jobs,
 * at zoom 1.0 and 1.5 (AUD-020: zoom re-renders the page).
 * AUD-020: Next/Prev draw other pages while an item is selected; a zoomed page stays reachable
 * and the selected highlight is scrolled into view.
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

/** Zoom in until the toolbar reads at least `percent`; returns the level reached. */
async function zoomTo(page: Page, percent: number): Promise<number> {
  const label = page.locator('.review-viewer__toolbar').getByText(/^\d+%$/)
  const level = async () => parseInt((await label.textContent()) ?? '100', 10)
  for (let i = 0; i < 12 && (await level()) < percent; i++) {
    await page.getByRole('button', { name: 'Zoom in' }).click()
  }
  await page.waitForTimeout(800)
  return level()
}

/** Backing-store width of the canvas: grows only when the page is re-rendered at a larger scale. */
const canvasBitmapWidth = (page: Page) =>
  page.locator('canvas.review-viewer__canvas').evaluate((c) => (c as HTMLCanvasElement).width)

/** Cheap fingerprint of the drawn pixels, to tell which page is on the canvas. */
const canvasFingerprint = (page: Page) =>
  page.locator('canvas.review-viewer__canvas').evaluate((el) => {
    const c = el as HTMLCanvasElement
    const ctx = c.getContext('2d')
    if (!ctx || c.width === 0) return ''
    const { data } = ctx.getImageData(0, 0, c.width, c.height)
    let h = 0
    for (let i = 0; i < data.length; i += 397) h = (h * 31 + data[i]) | 0
    return `${c.width}x${c.height}:${h}`
  })

for (const parser of ['docling', 'pymupdf'] as const) {
  for (const zoom of [100, 150]) {
    test(`highlights land on their values (${parser} job, zoom ${zoom}%)`, async ({ page }) => {
      const job = manifest()[parser]
      await openReview(page, job.filename)
      expect(await viewerOutcome(page)).toBe('rendered')
      const baseWidth = await canvasBitmapWidth(page)
      const reached = await zoomTo(page, zoom)
      // Zoom re-renders the page (sharp), rather than CSS-scaling a fixed bitmap (blurry).
      expect(Math.abs((await canvasBitmapWidth(page)) - (baseWidth * reached) / 100)).toBeLessThan(4)
      expect(await highlightMisses(page, job)).toEqual([])
      expect(reached).toBe(zoom)
    })
  }
}

test('Next/Prev draw other pages while an item is selected; zoomed page stays reachable', async ({ page }) => {
  const job = manifest().docling
  await openReview(page, job.filename)
  expect(await viewerOutcome(page)).toBe('rendered')
  await page.getByRole('tab', { name: /^All/ }).click()
  const [firstId] = Object.keys(job.expected_value_rects)
  await page.locator(`[data-item-id="${firstId}"]`).click()
  await page.waitForTimeout(800)

  const info = page.locator('.review-viewer__page-info')
  const startText = (await info.textContent()) ?? ''
  const startPixels = await canvasFingerprint(page)
  const [, start, total] = startText.match(/Page (\d+) of (\d+)/) ?? []
  expect(Number(total)).toBeGreaterThan(1)
  const other = Number(start) < Number(total) ? 'Next page' : 'Previous page'
  const back = other === 'Next page' ? 'Previous page' : 'Next page'

  await page.getByRole('button', { name: other }).click()
  await expect(info).not.toHaveText(startText)
  await expect(page.locator('.review-highlight-single')).toHaveCount(0)
  await page.waitForTimeout(800)
  // The other page is actually drawn, not just the label changed.
  expect(await canvasFingerprint(page)).not.toBe(startPixels)

  await page.getByRole('button', { name: back }).click()
  await expect(info).toHaveText(startText)
  await expect(page.locator('.review-highlight-single')).toHaveCount(1)

  await zoomTo(page, 200)
  // The zoomed page's left edge can be scrolled to (not pushed past the stage's left edge).
  const leftReachable = await page.evaluate(() => {
    const stage = document.querySelector('.review-viewer__stage') as HTMLElement | null
    const canvas = document.querySelector('canvas.review-viewer__canvas')
    if (!stage || !canvas) return false
    stage.scrollLeft = 0
    return canvas.getBoundingClientRect().left >= stage.getBoundingClientRect().left - 1
  })
  expect(leftReachable).toBe(true)

  // Selecting the item scrolls its highlight into the visible part of the stage.
  await page.locator(`[data-item-id="${firstId}"]`).click()
  await page.waitForTimeout(800)
  const visible = await page.evaluate(() => {
    const hl = document.querySelector('.review-highlight-single')?.getBoundingClientRect()
    const stage = document.querySelector('.review-viewer__stage')?.getBoundingClientRect()
    if (!hl || !stage) return false
    return hl.top >= stage.top && hl.bottom <= stage.bottom && hl.left >= stage.left && hl.right <= stage.right
  })
  expect(visible).toBe(true)
})
