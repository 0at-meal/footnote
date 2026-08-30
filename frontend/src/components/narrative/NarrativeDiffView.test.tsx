import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import NarrativeDiffView from './NarrativeDiffView'

describe('NarrativeDiffView', () => {
  it('renders loading state initially', () => {
    const html = renderToStaticMarkup(
      <NarrativeDiffView
        companyId="comp-1"
        earlierJobId="job-1"
        laterJobId="job-2"
        apiBase="http://localhost:8000"
      />,
    )
    expect(html).toContain('Narrative Delta Tracker')
    expect(html).toContain('Computing word-level narrative diff')
  })
})
