/**
 * AUD-019: at 1280x800 the review and audit-trail screens fit under the app bar. The page itself
 * does not scroll (so the sticky bar can never cover the page header or Export to Excel), the
 * item list starts above the fold, and the default selection is visible in the list.
 */
import { test, expect, type Page } from '@playwright/test'
import { manifest, openReview, viewerOutcome } from './helpers'

test.use({ viewport: { width: 1280, height: 800 } })

async function pageScrollsBy(page: Page): Promise<number> {
  return page.evaluate(() => {
    window.scrollTo(0, 10_000)
    return window.scrollY
  })
}

/** True when nothing covers the centre of the element (e.g. the sticky app bar). */
async function uncovered(page: Page, selector: string): Promise<boolean> {
  return page.evaluate((sel) => {
    const el = document.querySelector(sel)
    if (!el) return false
    const r = el.getBoundingClientRect()
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2)
    return !!hit && (hit === el || el.contains(hit))
  }, selector)
}

test('review screen: no page scroll, header and Export visible, list above the fold', async ({ page }) => {
  const job = manifest().docling
  await openReview(page, job.filename)
  expect(await viewerOutcome(page)).toBe('rendered')

  expect(await pageScrollsBy(page)).toBe(0)
  await expect(page.getByRole('heading', { name: 'Extraction Review' })).toBeInViewport()
  const exportButton = page.getByRole('button', { name: /Export to Excel/ }).first()
  await expect(exportButton).toBeInViewport()
  expect(await uncovered(page, '.review-header')).toBe(true)

  const firstOption = page.getByRole('option').first()
  const box = await firstOption.boundingBox()
  expect(box && box.y + box.height).toBeLessThanOrEqual(800)
  await expect(page.getByRole('option', { selected: true })).toBeInViewport()
})

test('audit trail screen: no page scroll, header visible', async ({ page }) => {
  const job = manifest().docling
  await openReview(page, job.filename)
  expect(await viewerOutcome(page)).toBe('rendered')
  await page.getByRole('button', { name: 'Export options' }).click()
  await page.getByRole('button', { name: 'View Audit Trail' }).first().click()
  await expect(page.locator('.audit-header')).toBeVisible()

  expect(await pageScrollsBy(page)).toBe(0)
  expect(await uncovered(page, '.audit-header')).toBe(true)
})
