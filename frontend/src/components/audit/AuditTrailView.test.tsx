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
})
