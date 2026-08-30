import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import LeaseScheduleCard from './LeaseScheduleCard'

describe('LeaseScheduleCard', () => {
  it('renders loading state initially', () => {
    const html = renderToStaticMarkup(
      <LeaseScheduleCard jobId="job-123" apiBase="http://localhost:8000" />,
    )
    expect(html).toContain('Loading Note 12 Lease Schedule')
  })
})
