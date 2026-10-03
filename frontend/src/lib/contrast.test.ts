import { describe, it, expect } from 'vitest'
import { contrastRatio, meetsAA } from './contrast'

// Reference values computed independently (Python, WCAG 2.1 formula) during the audit.
describe('contrastRatio (AUD-017)', () => {
  it.each([
    ['#14120F', '#FAF8F4', 17.63],
    ['#6B665E', '#FAF8F4', 5.37],
    ['#ECEAE5', '#0E0F12', 15.94],
    ['#9A978F', '#0E0F12', 6.57],
    ['#FFFFFF', '#7B93FF', 2.82],
    ['#B7791F', '#FAF8F4', 3.43],
  ])('%s on %s = %f', (fg, bg, expected) => {
    expect(contrastRatio(fg, bg)).toBeCloseTo(expected, 2)
  })

  it('is symmetric and AA thresholds are applied', () => {
    expect(contrastRatio('#000000', '#FFFFFF')).toBeCloseTo(21, 5)
    expect(contrastRatio('#FFFFFF', '#000000')).toBeCloseTo(21, 5)
    expect(meetsAA(4.5)).toBe(true)
    expect(meetsAA(4.49)).toBe(false)
    expect(meetsAA(3, 'large-or-ui')).toBe(true)
  })
})
