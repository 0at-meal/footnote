/**
 * Fiscal period formatting utility (FN-060).
 *
 * Derives user-friendly period labels such as "Q1 FY25" from filing document names
 * and filing years, falling back to "FY2025" or the year if no quarter is identified.
 */

export function formatFiscalPeriod(filename: string, filingYear?: number | null): string {
  // Detect quarter indicators like Q1, Q2, Q3, Q4, 10-Q, 10Q
  const qMatch = filename.match(/\b[Qq]([1-4])\b|[_\-.][Qq]([1-4])[_\-.]|[Qq]([1-4])/i)
  const quarterNum = qMatch ? qMatch[1] ?? qMatch[2] ?? qMatch[3] : null
  const quarter = quarterNum ? `Q${quarterNum}` : null

  if (filingYear) {
    const shortYear = filingYear >= 2000 ? String(filingYear).slice(-2) : String(filingYear)
    if (quarter) {
      return `${quarter} FY${shortYear}`
    }
    return `FY${filingYear}`
  }

  if (quarter) {
    return quarter
  }

  return '—'
}
