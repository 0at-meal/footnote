import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import ConcentrationCard from './ConcentrationCard'

describe('ConcentrationCard', () => {
  it('renders loading state initially', () => {
    const html = renderToStaticMarkup(
      <ConcentrationCard jobId="job-123" apiBase="http://localhost:8000" />,
    )
    expect(html).toContain('Loading Concentration Disclosures')
  })
})
