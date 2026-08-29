import { describe, it, expect, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import EdgarSearch from './EdgarSearch'

describe('EdgarSearch', () => {
  it('renders SEC EDGAR Direct Ingestion title and search placeholder', () => {
    const html = renderToStaticMarkup(
      <EdgarSearch apiBase="http://localhost:8000" onJobCreated={vi.fn()} />,
    )

    expect(html).toContain('SEC EDGAR Direct Ingestion')
    expect(html).toContain('Direct EDGAR API')
    expect(html).toContain('Search company by ticker')
  })
})
