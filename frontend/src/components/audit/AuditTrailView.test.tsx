import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import AuditTrailView from './AuditTrailView'

describe('AuditTrailView Component', () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
  })

  it('renders empty state guidance and Review CTA when no Excel model has been generated yet (Ticket 2.2)', () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      json: async () => ({ records: [] }),
    } as Response)

    const onReviewMock = vi.fn()

    const html = renderToStaticMarkup(
      <AuditTrailView
        jobId="job-empty-123"
        apiBase="http://localhost:8000"
        onBack={vi.fn()}
        onReview={onReviewMock}
      />
    )

    expect(html).toContain('Audit Trail &amp; Source Chain Lookup')
    expect(html).toContain('job-empty-123')
    expect(html).toContain(
      'No model yet — go to Review, approve the reconciliation bridge items, then click &#x27;Approve &amp; Generate Complete Financial Model&#x27;.'
    )
    expect(html).toContain('Go to Review → Approve &amp; Generate')
  })

  it('renders disabled Export Audit PDF button with tooltip when model is not ready (Ticket 2.1)', () => {
    const html = renderToStaticMarkup(
      <AuditTrailView
        jobId="job-123"
        apiBase="http://localhost:8000"
        onBack={vi.fn()}
        modelReady={false}
      />
    )

    expect(html).toContain('Export Audit PDF')
    expect(html).toContain('disabled=""')
    expect(html).toContain('Generate a model first: go to Review and click &#x27;Approve &amp; Generate&#x27;')
  })

  it('renders active download link when model is ready (Ticket 2.1)', () => {
    const html = renderToStaticMarkup(
      <AuditTrailView
        jobId="job-123"
        apiBase="http://localhost:8000"
        onBack={vi.fn()}
        modelReady={true}
      />
    )

    expect(html).toContain('<a ')
    expect(html).toContain('href="http://localhost:8000/api/jobs/job-123/audit-report"')
    expect(html).toContain('download="audit_report_job-123.pdf"')
  })

  it('renders rich empty state guide card with numbered checklist and actions (Ticket 4.1)', () => {
    const onReviewMock = vi.fn()
    const html = renderToStaticMarkup(
      <AuditTrailView
        jobId="job-456"
        apiBase="http://localhost:8000"
        onBack={vi.fn()}
        onReview={onReviewMock}
      />
    )

    expect(html).toContain('Model Provenance Not Available')
    expect(html).toContain('Upload and extract a 10-K filing.')
    expect(html).toContain('Review and approve line items in the Review tab.')
    expect(html).toContain('Approve &amp; Generate Complete Financial Model')
    expect(html).toContain('Go to Review Tab →')
    expect(html).toContain('Check again')
  })

  it('renders Refresh button in header for reloading provenance (Ticket 4.2)', () => {
    const html = renderToStaticMarkup(
      <AuditTrailView
        jobId="job-456"
        apiBase="http://localhost:8000"
        onBack={vi.fn()}
      />
    )

    expect(html).toContain('Refresh')
    expect(html).toContain('audit-header__refresh-btn')
  })

  it('renders fallback sheet options when provenance records are empty (Ticket 8.1)', () => {
    const html = renderToStaticMarkup(
      <AuditTrailView
        jobId="job-456"
        apiBase="http://localhost:8000"
        onBack={vi.fn()}
      />
    )

    expect(html).toContain('value="Reconciliation"')
    expect(html).toContain('value="Source_Inputs"')
  })

  it('derives sheet options dynamically from provenance records (Ticket 8.1)', () => {
    const mockProvenanceRecords = [
      {
        id: '1',
        job_id: 'job-multi-sheet',
        sheet_name: 'Reconciliation',
        cell_coord: 'C4',
        node_id: 'root_adj_ebitda',
        is_formula: false,
      },
      {
        id: '2',
        job_id: 'job-multi-sheet',
        sheet_name: 'Source_Inputs',
        cell_coord: 'B2',
        node_id: 'leaf_0_sbc',
        is_formula: false,
      },
      {
        id: '3',
        job_id: 'job-multi-sheet',
        sheet_name: 'Model_Summary',
        cell_coord: 'D10',
        node_id: 'agg_ebitda_margin',
        is_formula: true,
      },
    ]

    const html = renderToStaticMarkup(
      <AuditTrailView
        jobId="job-multi-sheet"
        apiBase="http://localhost:8000"
        onBack={vi.fn()}
        initialProvenanceRecords={mockProvenanceRecords}
      />
    )

    // Verify all 3 unique sheets appear in the dropdown
    expect(html).toContain('value="Model_Summary"')
    expect(html).toContain('Model_Summary')
    expect(html).toContain('value="Reconciliation"')
    expect(html).toContain('Reconciliation')
    expect(html).toContain('value="Source_Inputs"')
    expect(html).toContain('Source_Inputs')
  })
})
