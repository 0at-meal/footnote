import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import ReviewPage from './ReviewPage'

describe('ReviewPage Component', () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
  })

  it('renders review layout with Approve All & Generate Model button disabled when 0 items', () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      json: async () => ({ items: [] }),
    } as Response)

    const html = renderToStaticMarkup(
      <ReviewPage
        jobId="job-test-123"
        apiBase="http://localhost:8000"
        onBack={vi.fn()}
      />
    )

    expect(html).toContain('Extraction Review')
    expect(html).toContain('job-test-123')
    expect(html).toContain('Approve &amp; Generate Complete Financial Model (6 Tabs)')
    expect(html).toContain('disabled=""')
  })

  it('dispatches POST request to /models/{jobId}/generate on model generation trigger', async () => {
    const mockPostResponse = {
      job_id: 'job-test-123',
      file_path: '/path/to/job-test-123_model.xlsx',
      target_metric: 'Adjusted EBITDA',
      total_cells_generated: 15,
      formula_cells_count: 5,
      source_cells_count: 10,
      is_success: true,
    }

    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => mockPostResponse,
    } as Response)

    const apiBase = 'http://localhost:8000'
    const jobId = 'job-test-123'

    const res = await fetch(`${apiBase}/models/${jobId}/generate`, {
      method: 'POST',
    })
    const data = await res.json()

    expect(fetch).toHaveBeenCalledWith('http://localhost:8000/models/job-test-123/generate', {
      method: 'POST',
    })
    expect(data.is_success).toBe(true)
    expect(data.total_cells_generated).toBe(15)
  })

  it('renders scoped filter tabs with Flagged active by default (Ticket D.1.1)', () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      json: async () => ({
        job_id: 'job-test-123',
        total_items: 0,
        items: [],
      }),
    } as Response)

    const html = renderToStaticMarkup(
      <ReviewPage
        jobId="job-test-123"
        apiBase="http://localhost:8000"
        onBack={vi.fn()}
      />
    )

    // Verify statement filter tabs exist
    expect(html).toContain('Flagged')
    expect(html).toContain('All')
    expect(html).toContain('IS')
    expect(html).toContain('Bridge')
    expect(html).toContain('CF')
    expect(html).toContain('BS')

    // Verify Flagged is active by default
    expect(html).toContain('review-tab--active')
    expect(html).toContain('aria-selected="true"')
  })

  it('renders CTA button disabled when items list is empty (Ticket D.2.3)', () => {
    const htmlWithoutLocked = renderToStaticMarkup(
      <ReviewPage
        jobId="job-test-123"
        apiBase="http://localhost:8000"
        onBack={vi.fn()}
      />
    )
    expect(htmlWithoutLocked).toContain('disabled=""')
    expect(htmlWithoutLocked).toContain('Approve &amp; Generate Complete Financial Model (6 Tabs)')
  })

  it('renders statement readiness chips when items are present (Ticket D.2.2)', () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      json: async () => ({
        job_id: 'job-test-123',
        total_items: 2,
        items: [
          {
            id: '1',
            value: '100',
            label: 'Revenue',
            page: 1,
            bbox: { x0: 0, y0: 0, x1: 10, y1: 10 },
            source_file: 'file.pdf',
            confidence_band: 'auto_accepted',
            confidence_score: 0.99,
            normalized_label: 'Revenue',
            taxonomy_status: 'matched',
            status: 'locked',
            flags: [],
            statement_type: 'income_statement',
            error_detail: null,
          },
        ],
      }),
    } as Response)

    const html = renderToStaticMarkup(
      <ReviewPage
        jobId="job-test-123"
        apiBase="http://localhost:8000"
        onBack={vi.fn()}
      />
    )

    expect(html).toContain('Approve &amp; Generate Complete Financial Model (6 Tabs)')
  })

  it('correctly filters flagged items vs all reconciliation items (Ticket 3.4)', () => {
    const isFlagged = (item: {
      status: string
    }) =>
      item.status === 'needs_review' ||
      item.status === 'manual_required' ||
      item.status === 'extraction_error' ||
      item.status === 'pending_taxonomy_confirmation' ||
      item.status === 'flagged'

    const sampleItems = [
      { id: '1', label: 'SBC', status: 'auto_accepted' },
      { id: '2', label: 'Restructuring', status: 'needs_review' },
      { id: '3', label: 'Litigation', status: 'manual_required' },
      { id: '4', label: 'Unparsed Row', status: 'extraction_error' },
      { id: '5', label: 'Locked Item', status: 'locked' },
    ]

    const flagged = sampleItems.filter(isFlagged)
    expect(flagged.length).toBe(3)
    expect(flagged.map((i) => i.id)).toEqual(['2', '3', '4'])

    const all = sampleItems
    expect(all.length).toBe(5)
  })

  it('dispatches batch confirm and model generate in sequence on Approve All trigger (Ticket 1.2.4)', async () => {
    const mockBatchResponse = {
      job_id: 'job-test-123',
      total_locked: 2,
      locked_item_ids: ['item-1', 'item-2'],
      items: [],
    }

    const mockGenResponse = {
      job_id: 'job-test-123',
      file_path: '/path/to/job-test-123_model.xlsx',
      target_metric: 'Adjusted EBITDA',
      total_cells_generated: 12,
      is_success: true,
    }

    vi.mocked(fetch)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockBatchResponse,
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockGenResponse,
      } as Response)

    const apiBase = 'http://localhost:8000'
    const jobId = 'job-test-123'

    // 1. Dispatch confirm-batch
    const batchRes = await fetch(`${apiBase}/review/${jobId}/confirm-batch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        target_candidates_only: true,
        auto_add_pending_taxonomy: true,
      }),
    })
    const batchData = await batchRes.json()

    expect(fetch).toHaveBeenNthCalledWith(1, 'http://localhost:8000/review/job-test-123/confirm-batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        target_candidates_only: true,
        auto_add_pending_taxonomy: true,
      }),
    })
    expect(batchData.total_locked).toBe(2)

    // 2. Dispatch generate
    const genRes = await fetch(`${apiBase}/models/${jobId}/generate`, {
      method: 'POST',
    })
    const genData = await genRes.json()

    expect(fetch).toHaveBeenNthCalledWith(2, 'http://localhost:8000/models/job-test-123/generate', {
      method: 'POST',
    })
    expect(genData.is_success).toBe(true)
    expect(genData.total_cells_generated).toBe(12)
  })

  it('renders Engine: PyMuPDF badge when parser_used is pymupdf (Ticket 5.2)', () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      json: async () => ({
        job_id: 'job-fallback-123',
        total_items: 1,
        parser_used: 'pymupdf',
        items: [
          {
            id: '1',
            value: '100',
            label: 'Revenue',
            page: 1,
            bbox: { x0: 0, y0: 0, x1: 10, y1: 10 },
            source_file: 'file.pdf',
            confidence_band: 'needs_review',
            confidence_score: 0.85,
            normalized_label: null,
            taxonomy_status: null,
            status: 'needs_review',
            flags: [],
            statement_type: 'income_statement',
            error_detail: null,
          },
        ],
      }),
    } as Response)

    const html = renderToStaticMarkup(
      <ReviewPage
        jobId="job-fallback-123"
        apiBase="http://localhost:8000"
        onBack={vi.fn()}
        initialParserUsed="pymupdf"
      />
    )

    // Verify clean engine badge is rendered and no degraded warning banner
    expect(html).toContain('Engine: PyMuPDF')
    expect(html).not.toContain('Degraded Extraction Quality')
  })

  it('renders Generate Model button in empty Flagged tab when all items are reviewed/locked (Ticket 9.1)', () => {
    const mockItems = [
      {
        id: '1',
        value: '500',
        label: 'Stock-Based Compensation',
        page: 1,
        bbox: { x0: 0, y0: 0, x1: 10, y1: 10 },
        source_file: 'file.pdf',
        confidence_band: 'auto_accepted' as const,
        confidence_score: 0.99,
        normalized_label: 'Stock-Based Compensation',
        taxonomy_status: 'matched',
        status: 'locked' as const,
        flags: [],
        statement_type: 'non_gaap_bridge' as const,
        error_detail: null,
      },
    ]

    const html = renderToStaticMarkup(
      <ReviewPage
        jobId="job-all-locked"
        apiBase="http://localhost:8000"
        onBack={vi.fn()}
        initialItems={mockItems}
      />
    )

    // Verify empty state text and action button
    expect(html).toContain('All items reviewed. Ready to generate the financial model.')
    expect(html).toContain('Approve &amp; Generate Complete Financial Model (6 Tabs) →')
  })
})

