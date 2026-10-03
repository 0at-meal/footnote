// @vitest-environment jsdom
/**
 * AUD-020: the review viewer must let the reviewer browse pages while an item is selected,
 * zoom by re-rendering (not a CSS scale), fit the page to the stage width, and scroll the
 * selected item's highlight into view. Only pdf.js (loadPdf) and fetch are faked.
 */
import '../../test/setupDom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { createFakePdf } from '../../test/fakePdf'
import { PDF_RENDER_SCALE } from '../../lib/pdf/renderer'
import type { ReviewItem } from '../../types/review'

const pdf = vi.hoisted(() => ({ current: null as unknown }))

vi.mock('../../lib/pdf/renderer', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/pdf/renderer')>()
  return { ...actual, loadPdf: vi.fn(async () => pdf.current) }
})

import ReviewPage from './ReviewPage'

const item = (id: string, page: number): ReviewItem =>
  ({
    id,
    value: '1,000',
    label: `Item ${id}`,
    page,
    bbox: { x0: 100, y0: 500, x1: 200, y1: 520 },
    source_file: 'filing.pdf',
    confidence_band: 'needs_review',
    confidence_score: 0.9,
    status: 'needs_review',
    flags: [],
  }) as unknown as ReviewItem

function jsonResponse(body: unknown, ok = true, status = 200): Response {
  return { ok, status, json: async () => body } as Response
}

// Fake page is 600 x 800 pt at scale 1.
const PAGE_W = 600

async function openViewer() {
  // jsdom has no layout; report the canvas's CSS size as a browser would for an untransformed canvas.
  vi.spyOn(HTMLCanvasElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLCanvasElement) {
    const width = parseFloat(this.style.width) || 0
    const height = parseFloat(this.style.height) || 0
    return { width, height, top: 0, left: 0, right: width, bottom: height, x: 0, y: 0, toJSON: () => ({}) } as DOMRect
  })
  const { doc, stats } = createFakePdf(3, 5)
  pdf.current = doc
  vi.mocked(fetch).mockImplementation(async (input: RequestInfo | URL) => {
    if (String(input).endsWith('/items')) {
      return jsonResponse({ items: [item('a', 1), item('b', 3)], parser_used: 'docling' })
    }
    return jsonResponse({ detail: 'not found' }, false, 404)
  })
  const view = render(<ReviewPage jobId="job-viewer" apiBase="http://api" onBack={() => {}} />)
  await waitFor(() => expect(screen.getByRole('img', { name: /Highlight for Item a/ })).toBeTruthy())
  const canvas = view.container.querySelector('canvas.review-viewer__canvas') as HTMLCanvasElement
  return { view, stats, canvas }
}

const pageInfo = () => document.querySelector('.review-viewer__page-info')?.textContent

describe('ReviewPage viewer navigation and zoom (AUD-020)', () => {
  const originalFetch = globalThis.fetch
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
  })

  it('Next/Prev change the drawn page while an item is selected', async () => {
    const { stats } = await openViewer()
    expect(pageInfo()).toBe('Page 1 of 3')

    fireEvent.click(screen.getByRole('button', { name: 'Next page' }))
    await waitFor(() => expect(stats.completedRenders).toContain(2))
    expect(pageInfo()).toBe('Page 2 of 3')
    // The selected item is on page 1, so no highlight is drawn on page 2.
    expect(screen.queryByRole('img', { name: /Highlight for/ })).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Previous page' }))
    await waitFor(() => expect(screen.getByRole('img', { name: /Highlight for Item a/ })).toBeTruthy())
    expect(pageInfo()).toBe('Page 1 of 3')
  })

  it('zoom re-renders the page at the zoomed scale instead of CSS-scaling the canvas', async () => {
    const { canvas } = await openViewer()
    expect(canvas.style.width).toBe(`${Math.floor(PAGE_W * PDF_RENDER_SCALE)}px`)

    fireEvent.click(screen.getByRole('button', { name: 'Zoom in' }))
    const zoomedWidth = Math.floor(PAGE_W * PDF_RENDER_SCALE * 1.25)
    await waitFor(() => expect(canvas.style.width).toBe(`${zoomedWidth}px`))

    const wrap = canvas.parentElement as HTMLElement
    expect(wrap.style.transform).toBe('')
    // The highlight overlay is sized to the re-rendered page, so the box keeps its position.
    await waitFor(() => {
      const overlay = wrap.querySelector('.review-viewer__overlay') as HTMLElement
      expect(overlay.style.width).toBe(`${zoomedWidth}px`)
    })
  })

  it('Fit width scales the page to the stage width', async () => {
    const { view, canvas } = await openViewer()
    const stage = view.container.querySelector('.review-viewer__stage') as HTMLElement
    // 1232px stage minus 16px padding on each side leaves 1200px for the page.
    Object.defineProperty(stage, 'clientWidth', { configurable: true, value: 1232 })

    fireEvent.click(screen.getByRole('button', { name: 'Fit width' }))
    await waitFor(() => {
      const width = parseFloat(canvas.style.width)
      expect(width).toBeGreaterThanOrEqual(1198)
      expect(width).toBeLessThanOrEqual(1200)
    })
  })

  it('selecting an item scrolls its highlight into view', async () => {
    const scrolled: Element[] = []
    vi.spyOn(Element.prototype, 'scrollIntoView').mockImplementation(function (this: Element) {
      scrolled.push(this)
    })
    const { view } = await openViewer()

    fireEvent.click(view.container.querySelector('[data-item-id="b"]') as HTMLElement)
    const highlight = await screen.findByRole('img', { name: /Highlight for Item b/ })
    await waitFor(() => expect(scrolled).toContain(highlight))
    expect(pageInfo()).toBe('Page 3 of 3')
  })
})
