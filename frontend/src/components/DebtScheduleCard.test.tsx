import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import DebtScheduleCard from './DebtScheduleCard'

describe('DebtScheduleCard', () => {
  it('renders loading state initially', () => {
    const html = renderToStaticMarkup(
      <DebtScheduleCard jobId="job-123" apiBase="http://localhost:8000" />,
    )
    expect(html).toContain('Loading Note 8 Debt Schedule')
  })
})
