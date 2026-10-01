import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import DebtScheduleCard, { type DebtSchedule } from './DebtScheduleCard'

const mockPassingSchedule: DebtSchedule = {
  job_id: 'job-123',
  footnote_title: 'Note 8: Debt and Financing Arrangements',
  total_debt: 2500,
  weighted_avg_rate: 4.85,
  is_confirmed: false,
  tranches: [
    {
      id: 't-1',
      instrument_name: '5.25% Senior Notes due 2028',
      principal_amount: 1500,
      principal_text: '1,500',
      interest_rate: 5.25,
      rate_text: '5.25%',
      maturity_year: 2028,
      senior_subordinated: 'Senior',
      is_floating: false,
      spread: null,
      benchmark: null,
      page: 45,
      bbox: { x0: 50, y0: 100, x1: 500, y1: 120 },
    },
    {
      id: 't-2',
      instrument_name: 'Term Loan B due 2030',
      principal_amount: 1000,
      principal_text: '1,000',
      interest_rate: 4.25,
      rate_text: 'SOFR + 3.00%',
      maturity_year: 2030,
      senior_subordinated: 'Senior Secured',
      is_floating: true,
      spread: 3.0,
      benchmark: 'SOFR',
      page: 45,
      bbox: { x0: 50, y0: 125, x1: 500, y1: 145 },
    },
  ],
}

const mockFailingSchedule: DebtSchedule = {
  ...mockPassingSchedule,
  total_debt: 3000, // tranches sum to 2500, mismatch by 500
}

describe('DebtScheduleCard', () => {
  it('renders loading state initially when initialSchedule is not provided', () => {
    const html = renderToStaticMarkup(
      <DebtScheduleCard jobId="job-123" apiBase="http://localhost:8000" />,
    )
    expect(html).toContain('Loading Note 8 Debt Schedule')
  })

  it('renders Total Principal hero number and weighted avg coupon', () => {
    const html = renderToStaticMarkup(
      <DebtScheduleCard
        jobId="job-123"
        apiBase="http://localhost:8000"
        initialSchedule={mockPassingSchedule}
      />,
    )
    expect(html).toContain('Total Principal')
    expect(html).toContain('$2,500M')
    expect(html).toContain('4.85%')
    expect(html).toContain('Confirm Debt Schedule')
  })

  it('renders tie-out PASS badge when tranche principals sum matches total debt', () => {
    const html = renderToStaticMarkup(
      <DebtScheduleCard
        jobId="job-123"
        apiBase="http://localhost:8000"
        initialSchedule={mockPassingSchedule}
      />,
    )
    expect(html).toContain('Tie-out: PASS (Tranches sum to Total Principal)')
  })

  it('renders tie-out FAIL badge when tranche principals mismatch total debt', () => {
    const html = renderToStaticMarkup(
      <DebtScheduleCard
        jobId="job-123"
        apiBase="http://localhost:8000"
        initialSchedule={mockFailingSchedule}
      />,
    )
    expect(html).toContain('Tie-out: FAIL (Diff $500M)')
  })

  it('renders maturity ladder chart with accessible text alternative and visual bars', () => {
    const html = renderToStaticMarkup(
      <DebtScheduleCard
        jobId="job-123"
        apiBase="http://localhost:8000"
        initialSchedule={mockPassingSchedule}
      />,
    )
    expect(html).toContain('Maturity Ladder by Year')
    // Screen reader accessible alternative
    expect(html).toContain('Maturity schedule summary:')
    expect(html).toContain('Year 2028: $1,500M;')
    expect(html).toContain('Year 2030: $1,000M;')
    // img role with aria-label
    expect(html).toContain('role="img"')
    expect(html).toContain('aria-label="Maturity schedule chart by year showing principal due per maturity period"')
  })

  it('renders tranches table via DataTable with formatted columns', () => {
    const html = renderToStaticMarkup(
      <DebtScheduleCard
        jobId="job-123"
        apiBase="http://localhost:8000"
        initialSchedule={mockPassingSchedule}
      />,
    )
    expect(html).toContain('5.25% Senior Notes due 2028')
    expect(html).toContain('Term Loan B due 2030')
    expect(html).toContain('fn-data-table-container')
    expect(html).toContain('($M)') // units in header
    expect(html).toContain('$1,500')
    expect(html).toContain('$1,000')
  })
})
