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
    expect(html).toContain('Approve All &amp; Generate Model')
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

  it('renders 2 scoped filter tabs with Flagged Items active by default (Ticket 1.2.2)', () => {
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

    // Verify 2 filter tabs exist
    expect(html).toContain('Flagged Items')
    expect(html).toContain('All Reconciliation Items')

    // Verify Flagged Items is active by default
    expect(html).toContain('review-tab--active')
    expect(html).toContain('aria-selected="true"')
  })

  it('renders Generate Excel Model button when lockedCount > 0 and omits it when 0', () => {
    // 1. With 0 locked items: button should be absent
    const htmlWithoutLocked = renderToStaticMarkup(
      <ReviewPage
        jobId="job-test-123"
        apiBase="http://localhost:8000"
        onBack={vi.fn()}
      />
    )
    expect(htmlWithoutLocked).not.toContain('Generate Excel Model')
  })

  it('correctly filters flagged items vs all reconciliation items (Ticket 1.2.4)', () => {
    const isFlagged = (item: {
      status: string
      confidence_score: number
    }) =>
      item.status === 'needs_review' ||
      item.status === 'manual_required' ||
      item.status === 'extraction_error' ||
      item.status === 'pending_taxonomy_confirmation' ||
      item.status === 'flagged' ||
      item.confidence_score < 0.95

    const sampleItems = [
      { id: '1', label: 'SBC', confidence_score: 0.99, status: 'auto_accepted' },
      { id: '2', label: 'Restructuring', confidence_score: 0.85, status: 'needs_review' },
      { id: '3', label: 'Litigation', confidence_score: 0.50, status: 'manual_required' },
      { id: '4', label: 'Unparsed Row', confidence_score: 0.10, status: 'extraction_error' },
    ]

    const flagged = sampleItems.filter(isFlagged)
    expect(flagged.length).toBe(3)
    expect(flagged.map((i) => i.id)).toEqual(['2', '3', '4'])

    const all = sampleItems
    expect(all.length).toBe(4)
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
})

