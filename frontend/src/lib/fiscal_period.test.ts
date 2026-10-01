import { describe, it, expect } from 'vitest'
import { formatFiscalPeriod } from './fiscal_period'

describe('formatFiscalPeriod (FN-060)', () => {
  it('formats Q1 10-Q filing with filing year as Q1 FY25', () => {
    expect(formatFiscalPeriod('AAPL_10-Q_Q1_2025.pdf', 2025)).toBe('Q1 FY25')
    expect(formatFiscalPeriod('tsla-q1-2025.pdf', 2025)).toBe('Q1 FY25')
    expect(formatFiscalPeriod('MSFT_Q3_2024.pdf', 2024)).toBe('Q3 FY24')
  })

  it('formats annual 10-K filing as FY2023', () => {
    expect(formatFiscalPeriod('AAPL_10-K_2023.pdf', 2023)).toBe('FY2023')
    expect(formatFiscalPeriod('msft_annual.pdf', 2022)).toBe('FY2022')
  })

  it('falls back to dash when neither year nor quarter is present', () => {
    expect(formatFiscalPeriod('report.pdf', null)).toBe('—')
  })
})
