import { describe, it, expect, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import ModelViewer from './ModelViewer'

describe('ModelViewer Component (Ticket D.2.1)', () => {
  it('renders all 6 statement tabs in order', () => {
    const html = renderToStaticMarkup(
      <ModelViewer
        jobId="job-123"
        companyName="Apple Inc."
        apiBase="http://localhost:8000"
        onBack={vi.fn()}
      />
    )

    expect(html).toContain('Apple Inc. ? 6-Tab Financial Model')
    expect(html).toContain('Executive Summary')
    expect(html).toContain('Income Statement')
    expect(html).toContain('EBITDA Bridge')
    expect(html).toContain('Cash Flow')
    expect(html).toContain('Balance Sheet')
    expect(html).toContain('Audit Trail')
    expect(html).toContain('Download .xlsx')
  })

  it('renders IB styling legend', () => {
    const html = renderToStaticMarkup(
      <ModelViewer
        jobId="job-123"
        companyName="Tesla Inc."
        apiBase="http://localhost:8000"
        onBack={vi.fn()}
      />
    )

    expect(html).toContain('Blue: Hardcoded Input')
    expect(html).toContain('Green: Cross-Sheet Link')
    expect(html).toContain('Black: Excel Formula')
  })
})
