// @vitest-environment jsdom
import '../../test/setupDom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { createFakePdf, deferred } from '../../test/fakePdf'
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
    bbox: { x0: 100, y0: 100, x1: 200, y1: 120 },
    source_file: 'filing.pdf',
    confidence_band: 'needs_review',
    confidence_score: 0.9,
    status: 'needs_review',
    flags: [],
  }) as unknown as ReviewItem

function jsonResponse(body: unknown, ok = true, status = 200): Response {
  return { ok, status, json: async () => body } as Response
}

describe('ReviewPage PDF render race (AUD-001)', () => {
  const originalFetch = globalThis.fetch
  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
  })
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  it('renders the selected item page when the PDF loads before the item list', async () => {
    const { doc, stats } = createFakePdf(3, 40)
    pdf.current = doc
    const items = deferred<Response>()
    vi.mocked(fetch).mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/items')) return items.promise
      return jsonResponse({ detail: 'not found' }, false, 404)
    })

    render(<ReviewPage jobId="job-race" apiBase="http://api" onBack={() => {}} />)

    // PDF is loaded and page 1 starts rendering before the items arrive.
    await waitFor(() => expect(stats.renderCalls.length).toBeGreaterThan(0))
    await act(async () => {
      items.resolve(jsonResponse({ items: [item('a', 2), item('b', 3)], parser_used: 'docling' }))
    })

    await waitFor(() => expect(stats.completedRenders).toContain(2), { timeout: 2000 })
    expect(stats.canvasConflicts).toBe(0)
    expect(screen.queryByText(/Page Rendering Error/i)).toBeNull()
    expect(screen.queryByText(/Cannot use the same canvas/i)).toBeNull()
  })
})
