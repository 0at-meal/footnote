// @vitest-environment jsdom
/**
 * AUD-019: review screen layout. The item list comes first (footnote schedules live in their own
 * tab), long lists are virtualized, the default selection is in the visible tab, the pending
 * taxonomy panel has no inner scroll box, and the back button shows one arrow.
 * Only pdf.js (loadPdf) and fetch are faked; ReviewPage and its child cards are real.
 */
import '../../test/setupDom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'
import { createFakePdf } from '../../test/fakePdf'
import { stubReviewListLayout } from '../../test/listLayout'
import type { ReviewItem } from '../../types/review'

const pdf = vi.hoisted(() => ({ current: null as unknown }))

vi.mock('../../lib/pdf/renderer', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/pdf/renderer')>()
  return { ...actual, loadPdf: vi.fn(async () => pdf.current) }
})

import ReviewPage from './ReviewPage'

const item = (id: string, page: number, status: string, extra: Partial<ReviewItem> = {}): ReviewItem =>
  ({
    id,
    value: '1,000',
    label: `Item ${id}`,
    page,
    bbox: { x0: 100, y0: 500, x1: 200, y1: 520 },
    source_file: 'filing.pdf',
    confidence_band: status === 'locked' ? 'auto_accepted' : 'needs_review',
    confidence_score: 0.9,
    status,
    flags: [],
    ...extra,
  }) as unknown as ReviewItem

// SYNTHETIC debt footnote for the card (not filing data).
const SYNTHETIC_DEBT = {
  job_id: 'job-layout',
  footnote_title: 'Synthetic Note 8 Debt',
  tranches: [
    {
      id: 't1',
      instrument_name: 'Synthetic Term Loan',
      principal_amount: 100,
      principal_text: '100',
      interest_rate: 5,
      rate_text: '5%',
      maturity_year: 2030,
      senior_subordinated: 'senior',
      is_floating: false,
      spread: null,
      benchmark: null,
      page: 1,
      bbox: { x0: 0, y0: 0, x1: 10, y1: 10 },
    },
  ],
  total_debt: 100,
  weighted_avg_rate: 5,
  is_confirmed: false,
}

function jsonResponse(body: unknown, ok = true, status = 200): Response {
  return { ok, status, json: async () => body } as Response
}

function serve(items: ReviewItem[], debt: unknown = null) {
  stubReviewListLayout()
  pdf.current = createFakePdf(3, 5).doc
  vi.mocked(fetch).mockImplementation(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/items')) return jsonResponse({ items, parser_used: 'docling' })
    if (url.endsWith('/footnote/job-layout/debt') && debt) return jsonResponse(debt)
    return jsonResponse({ detail: 'not found' }, false, 404)
  })
  return render(<ReviewPage jobId="job-layout" apiBase="http://api" onBack={() => {}} />)
}

describe('ReviewPage layout (AUD-019)', () => {
  const originalFetch = globalThis.fetch
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
  })

  it('selects the first item of the active (Flagged) tab, not a locked item hidden by the filter', async () => {
    serve([item('locked-1', 1, 'locked'), item('flag-1', 2, 'needs_review'), item('flag-2', 3, 'needs_review')])
    const list = await screen.findByRole('listbox', { name: 'Extracted items list' })
    await waitFor(() => expect(within(list).getByRole('option', { selected: true }).getAttribute('data-item-id')).toBe('flag-1'))
    await waitFor(() => expect(document.querySelector('.review-viewer__page-info')?.textContent).toBe('Page 2 of 3'))
  })

  it('switching to a tab that does not contain the selection selects that tab’s first item', async () => {
    serve([
      item('flag-1', 2, 'needs_review', { statement_type: 'non_gaap_bridge' } as Partial<ReviewItem>),
      item('bs-1', 3, 'locked', { statement_type: 'balance_sheet' } as Partial<ReviewItem>),
    ])
    const list = await screen.findByRole('listbox', { name: 'Extracted items list' })
    await waitFor(() => expect(within(list).getByRole('option', { selected: true }).getAttribute('data-item-id')).toBe('flag-1'))
    fireEvent.click(screen.getByRole('tab', { name: /^BS/ }))
    await waitFor(() =>
      expect(screen.getByRole('option', { selected: true }).getAttribute('data-item-id')).toBe('bs-1'),
    )
  })

  it('renders the item list before any footnote schedule; schedules live in their own tab', async () => {
    const view = serve([item('flag-1', 1, 'needs_review')], SYNTHETIC_DEBT)
    const list = await screen.findByRole('listbox', { name: 'Extracted items list' })
    const sidebar = view.container.querySelector('.review-sidebar') as HTMLElement
    // Give the card time to load; it must not appear in the item list view.
    await new Promise((r) => setTimeout(r, 50))
    expect(within(sidebar).queryByText('Synthetic Note 8 Debt')).toBeNull()
    expect(list).toBeTruthy()

    fireEvent.click(screen.getByRole('tab', { name: /Footnotes/ }))
    expect(await within(sidebar).findByText('Synthetic Note 8 Debt')).toBeTruthy()
  })

  it('virtualizes long lists instead of mounting every card', async () => {
    const many = Array.from({ length: 954 }, (_, n) => item(`i${n}`, 1 + (n % 3), 'needs_review'))
    serve(many)
    const list = await screen.findByRole('listbox', { name: 'Extracted items list' })
    await waitFor(() => expect(within(list).getAllByRole('option').length).toBeGreaterThan(0))
    expect(within(list).getAllByRole('option').length).toBeLessThan(60)
  })

  it('the pending-taxonomy panel has no inner scroll box (no nested scrolling)', async () => {
    const view = serve([item('tax-1', 1, 'pending_taxonomy_confirmation'), item('tax-2', 1, 'pending_taxonomy_confirmation')])
    await screen.findByText(/Pending Taxonomy Confirmations/)
    const panel = view.container.querySelector('.review-bulk-taxonomy-panel') as HTMLElement
    const scrollers = Array.from(panel.querySelectorAll<HTMLElement>('*')).filter(
      (el) => el.style.overflowY === 'auto' || el.style.overflowY === 'scroll' || el.style.maxHeight !== '',
    )
    expect(scrollers).toEqual([])
  })

  it('the back button shows a single arrow', async () => {
    serve([item('flag-1', 1, 'needs_review')])
    const back = await screen.findByRole('button', { name: 'Back to queue' })
    expect(back.textContent).not.toContain('←')
  })
})
