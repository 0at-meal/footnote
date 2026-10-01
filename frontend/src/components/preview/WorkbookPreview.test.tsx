import { describe, it, expect, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import WorkbookPreview from './WorkbookPreview'
import { DEFAULT_CHECKS, DEFAULT_SAMPLE_ROWS } from './sampleData'

describe('WorkbookPreview (FN-067)', () => {
  it('renders workbook preview with sheet name, company, and period', () => {
    const html = renderToStaticMarkup(
      <WorkbookPreview
        jobId="job-123"
        companyName="Apple Inc."
        period="Q3 FY25"
        sheetName="EBITDA_Bridge"
        onExportExcel={vi.fn()}
      />,
    )
    expect(html).toContain('EBITDA_Bridge')
    expect(html).toContain('Apple Inc. · Q3 FY25')
  })

  it('renders checks summary badge and payoff moment', () => {
    const html = renderToStaticMarkup(
      <WorkbookPreview
        jobId="job-123"
        companyName="Apple Inc."
        checks={DEFAULT_CHECKS}
        onExportExcel={vi.fn()}
      />,
    )
    expect(html).toContain('5/5 checks passed')
    expect(html).toContain('Ready for modeling')
  })

  it('renders read-only grid with line items, formulas, and flagged cells', () => {
    const html = renderToStaticMarkup(
      <WorkbookPreview
        jobId="job-123"
        companyName="Apple Inc."
        rows={DEFAULT_SAMPLE_ROWS}
        onExportExcel={vi.fn()}
      />,
    )
    expect(html).toContain('Operating Income (EBIT)')
    expect(html).toContain('Stock-Based Compensation')
    expect(html).toContain('Adjusted EBITDA')
    expect(html).toContain('=SUM(B4:B8)')
    expect(html).toContain('[Manual Required]')
  })

  it('renders primary Export to Excel button', () => {
    const html = renderToStaticMarkup(
      <WorkbookPreview
        jobId="job-123"
        companyName="Apple Inc."
        onExportExcel={vi.fn()}
      />,
    )
    expect(html).toContain('Export to Excel')
  })

  it('renders draft warning status when unverified items exist', () => {
    const html = renderToStaticMarkup(
      <WorkbookPreview
        jobId="job-123"
        companyName="Apple Inc."
        rows={DEFAULT_SAMPLE_ROWS}
        onExportExcel={vi.fn()}
      />,
    )
    // In DEFAULT_SAMPLE_ROWS, there is 1 needs_review and 1 manual_required -> 2 unverified items
    expect(html).toContain('DRAFT: 2 items unverified')
  })
})
