import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import RiskRedlineView from './RiskRedlineView'

describe('RiskRedlineView', () => {
  it('renders loading state initially', () => {
    const html = renderToStaticMarkup(
      <RiskRedlineView
        companyId="comp-1"
        earlierJobId="job-1"
        laterJobId="job-2"
        apiBase="http://localhost:8000"
      />,
    )
    expect(html).toContain('Risk Factor Redline Tracker')
    expect(html).toContain('Comparing Risk Factor disclosures')
  })
})
