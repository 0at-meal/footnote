/**
 * AUD-001 runtime check: the review PDF must render on every open, including when the
 * item list arrives after the PDF has loaded (the ordering that triggered pdf.js's
 * "Cannot use the same canvas during multiple render() operations").
 */
import { test, expect } from '@playwright/test'
import { manifest, openReview, viewerOutcome } from './helpers'

const RUNS = 20

test('review PDF renders on 20 consecutive opens', async ({ page }) => {
  const { filename } = manifest()
  const outcomes: string[] = []
  for (let i = 0; i < RUNS; i++) {
    await openReview(page, filename)
    outcomes.push(await viewerOutcome(page))
  }
  console.log(`natural opens: ${outcomes.filter((o) => o === 'error').length}/${RUNS} failed`)
  expect(outcomes.filter((o) => o === 'error')).toHaveLength(0)
})

test('review PDF renders on 20 opens when items arrive after the PDF (forced, CPU x6)', async ({ page }) => {
  const { filename } = manifest()
  const cdp = await page.context().newCDPSession(page)
  await cdp.send('Emulation.setCPUThrottlingRate', { rate: 6 })

  await page.route('**/review/*/items', async (route) => {
    // Hold the item list until pdf.js has loaded the document and started drawing page 1.
    await page
      .waitForFunction(() => /\bof\b/.test(document.querySelector('.review-viewer__page-info')?.textContent ?? ''), null, {
        timeout: 30_000,
      })
      .catch(() => undefined)
    await route.continue()
  })

  const outcomes: string[] = []
  for (let i = 0; i < RUNS; i++) {
    await openReview(page, filename)
    outcomes.push(await viewerOutcome(page))
  }
  console.log(`forced slow-items opens: ${outcomes.filter((o) => o === 'error').length}/${RUNS} failed`)
  expect(outcomes.filter((o) => o === 'error')).toHaveLength(0)
})
