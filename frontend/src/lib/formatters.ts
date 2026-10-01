/**
 * Financial number formatting utilities.
 */

/**
 * Format numeric values to display negative numbers in parentheses: (1,234.56).
 */
export function formatNegativeInParens(val: unknown): string {
  if (typeof val === 'number') {
    if (isNaN(val)) return '—'
    if (val < 0) {
      return `(${Math.abs(val).toLocaleString()})`
    }
    return val.toLocaleString()
  }
  if (typeof val === 'string') {
    const trimmed = val.trim()
    if (trimmed.startsWith('-') && !isNaN(Number(trimmed.slice(1).replace(/,/g, '')))) {
      const num = Math.abs(Number(trimmed.replace(/,/g, '')))
      return `(${num.toLocaleString()})`
    }
    return val
  }
  return String(val ?? '')
}
