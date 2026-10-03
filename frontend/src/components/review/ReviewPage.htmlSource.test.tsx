// @vitest-environment jsdom
/**
 * AUD-018 / D9: an item from an SEC HTML filing is identified by its locator type (not the file
 * extension) and links out to sec.gov with the CIK-qualified Archives URL. No iframe to the
 * non-existent /filings/{job}/html route, and no `allow-same-origin allow-scripts` sandbox.
 * Locator values are SYNTHETIC.
 */
import '../../test/setupDom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { createFakePdf } from '../../test/fakePdf'
import type { ReviewItem } from '../../types/review'

const pdf = vi.hoisted(() => ({ current: null as unknown }))

vi.mock('../../lib/pdf/renderer', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/pdf/renderer')>()
  return { ...actual, loadPdf: vi.fn(async () => pdf.current) }
})

import ReviewPage from './ReviewPage'

const SYN_URL = 'https://www.sec.gov/Archives/edgar/data/9999999/000999999926000001/synthetic-20260630.htm'

const htmlItem = (locator: Record<string, unknown>, sourceFile = 'synthetic-20260630.htm'): ReviewItem =>
  ({
    id: 'h1',
    value: '1,000',
    label: 'Reconciliation > 2026 > Net income',
    page: 1,
    bbox: { x0: 0, y0: 0, x1: 1000, y1: 1000 },
    source_file: sourceFile,
    locator: {
      type: 'html',
      accession: '0009999999-26-000001',
      document: 'synthetic-20260630.htm',
      element_path: '/html/body/table[1]/tr[2]/td[2]',
      ...locator,
    },
    confidence_band: 'needs_review',
    confidence_score: 0.9,
    normalized_label: null,
    taxonomy_status: null,
    status: 'needs_review',
    flags: [],
  }) as unknown as ReviewItem

function open(item: ReviewItem) {
  pdf.current = createFakePdf(1, 5).doc
  return render(<ReviewPage jobId="job-html" apiBase="http://api" onBack={() => {}} initialItems={[item]} />)
}

describe('ReviewPage HTML source (AUD-018)', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 404, json: async () => ({}) }) as Response))
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('links out to sec.gov with the CIK-qualified URL and a text fragment; no iframe', () => {
    const view = open(htmlItem({ cik: '9999999', url: SYN_URL }))
    const link = screen.getByRole('link', { name: /Open on sec\.gov/ })
    expect(link.getAttribute('href')).toBe(`${SYN_URL}#:~:text=Net%20income`)
    expect(link.getAttribute('target')).toBe('_blank')
    expect(link.getAttribute('rel')).toContain('noopener')
    expect(view.container.querySelector('iframe')).toBeNull()
  })

  it('shows no link (rather than a broken one) when the stored URL is not a CIK-qualified Archives URL', () => {
    const view = open(htmlItem({ url: 'https://www.sec.gov/Archives/edgar/data/000999999926000001/synthetic-20260630.htm' }))
    expect(screen.queryByRole('link', { name: /Open on sec\.gov/ })).toBeNull()
    expect(screen.getByText(/No sec\.gov link/)).toBeTruthy()
    expect(view.container.querySelector('iframe')).toBeNull()
  })

  it('chooses the viewer by locator type, not file extension', () => {
    const pdfItem = {
      ...htmlItem({}),
      source_file: 'misnamed.html',
      locator: { type: 'pdf', page: 1, bbox: { x0: 0, y0: 0, x1: 10, y1: 10 }, source_file: 'misnamed.html' },
    } as unknown as ReviewItem
    const view = open(pdfItem)
    expect(view.container.querySelector('canvas.review-viewer__canvas')).not.toBeNull()
    expect(view.container.querySelector('iframe')).toBeNull()
  })
})
