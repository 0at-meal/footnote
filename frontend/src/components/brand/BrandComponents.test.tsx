import { describe, it, expect, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { Wordmark } from './Wordmark'
import { SourceChip } from './SourceChip'
import { EmptyState } from './EmptyState'

describe('Brand Components (FN-066)', () => {
  it('renders Wordmark with superscript marker', () => {
    const html = renderToStaticMarkup(<Wordmark size="md" marker="*" />)
    expect(html).toContain('fn-wordmark')
    expect(html).toContain('footnote')
    expect(html).toContain('fn-wordmark__marker')
    expect(html).toContain('*')
  })

  it('renders SourceChip with citation text and page', () => {
    const html = renderToStaticMarkup(
      <SourceChip
        sourceFile="10k_2023.pdf"
        page={14}
        label="D&A"
        value="$350.0M"
        snippet="Depreciation was $350 million"
      />,
    )
    expect(html).toContain('fn-source-chip')
    expect(html).toContain('[')
    expect(html).toContain('p.14')
    expect(html).toContain(']')
    expect(html).toContain('aria-label="View source citation: 10k_2023.pdf, page 14 for D&amp;A"')
  })

  it('renders EmptyState with variants and CTAs', () => {
    const handleAction = vi.fn()
    const html = renderToStaticMarkup(
      <EmptyState
        variant="no-filings"
        actionLabel="Upload First Filing"
        onAction={handleAction}
      />,
    )
    expect(html).toContain('fn-empty-state--no-filings')
    expect(html).toContain('No filings in processing queue')
    expect(html).toContain('Upload First Filing')
  })
})
