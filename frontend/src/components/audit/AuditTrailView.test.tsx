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

  it('renders empty state guidance when no Excel model has been generated yet', () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      json: async () => ({ records: [] }),
    } as Response)

    const html = renderToStaticMarkup(
      <AuditTrailView
        jobId="job-empty-123"
        apiBase="http://localhost:8000"
        onBack={vi.fn()}
        onReview={vi.fn()}
      />
    )

    expect(html).toContain('Audit Trail &amp; Source Chain Lookup')
    expect(html).toContain('job-empty-123')
  })
})
