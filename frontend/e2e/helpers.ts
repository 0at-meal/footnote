import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { expect, type Page } from '@playwright/test'

export type E2EManifest = {
  job_id: string
  filename: string
  status: string
  parser_used: string
  review_items: number
  expected_value_rects: Record<string, [number, number, number, number]>
}

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
