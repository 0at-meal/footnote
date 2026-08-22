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

  it('renders empty state guidance and Review CTA when no Excel model has been generated yet (Ticket 1.4.1)', () => {
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
      'Model not yet generated. Approve items and click &#x27;Generate Model&#x27; to view cell-level audit trail.'
    )
    expect(html).toContain('Go to Review Tab →')
  })
})
