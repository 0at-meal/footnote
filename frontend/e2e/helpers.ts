import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { expect, type Page } from '@playwright/test'

export type E2EJob = {
  job_id: string
  filename: string
  status: string
  parser_used: string
  review_items: number
  expected_value_rects: Record<string, [number, number, number, number]>
}

export type E2EManifest = { docling: E2EJob; pymupdf: E2EJob }

export function manifest(): E2EManifest {
  const dir = process.env.FN_E2E_DATA_DIR
  if (!dir) throw new Error('FN_E2E_DATA_DIR not set (playwright.config.ts seeds it)')
  return JSON.parse(readFileSync(join(dir, 'e2e_manifest.json'), 'utf8')) as E2EManifest
}

export async function openReview(page: Page, filename: string): Promise<void> {
  await page.goto('/')
  await page.getByRole('button', { name: `Review ${filename}` }).click()
}

/** Wait for the viewer to settle, then report whether the page canvas is showing. */
export async function viewerOutcome(page: Page): Promise<'rendered' | 'error'> {
  await expect(page.locator('.review-viewer__page-info')).toContainText(' of ', { timeout: 60_000 })
  // Allow any in-flight re-render (items arriving, selection change) to finish or fail.
  await page.waitForTimeout(1500)
  const errors = await page.locator('.review-viewer__error').count()
  const wrapVisible = await page.locator('.review-viewer__canvas-wrap').isVisible()
  const canvasWidth = await page
    .locator('canvas.review-viewer__canvas')
    .evaluate((c) => (c as HTMLCanvasElement).width)
  return errors === 0 && wrapVisible && canvasWidth > 0 ? 'rendered' : 'error'
}

/** Number of non-white pixels drawn on the review canvas (proves the page was actually rendered). */
export async function canvasInkPixels(page: Page): Promise<number> {
  return page.locator('canvas.review-viewer__canvas').evaluate((el) => {
    const canvas = el as HTMLCanvasElement
    const ctx = canvas.getContext('2d')
    if (!ctx || canvas.width === 0 || canvas.height === 0) return 0
    const { data } = ctx.getImageData(0, 0, canvas.width, canvas.height)
    let ink = 0
    for (let i = 0; i < data.length; i += 4) {
      if (data[i + 3] > 0 && (data[i] < 200 || data[i + 1] < 200 || data[i + 2] < 200)) ink += 1
    }
    return ink
  })
}

/** Highlight box of the selected item in 0-1000 page space, measured from the rendered DOM. */
export async function highlightInPageSpace(page: Page): Promise<[number, number, number, number] | null> {
  return page.evaluate(() => {
    const hl = document.querySelector('.review-highlight-single')
    const canvas = document.querySelector('canvas.review-viewer__canvas')
    if (!hl || !canvas) return null
    const h = hl.getBoundingClientRect()
    const c = canvas.getBoundingClientRect()
    if (c.width === 0 || c.height === 0) return null
    return [
      ((h.left - c.left) / c.width) * 1000,
      ((h.top - c.top) / c.height) * 1000,
      ((h.right - c.left) / c.width) * 1000,
      ((h.bottom - c.top) / c.height) * 1000,
    ] as [number, number, number, number]
  })
}

/** True when the centre of `value` (0-1000 rect) lies inside `box`, with a small tolerance. */
export function centreInside(value: number[], box: number[], tol = 8): boolean {
  const cx = (value[0] + value[2]) / 2
  const cy = (value[1] + value[3]) / 2
  return cx >= box[0] - tol && cx <= box[2] + tol && cy >= box[1] - tol && cy <= box[3] + tol
}
