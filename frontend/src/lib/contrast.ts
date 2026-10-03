/**
 * WCAG 2.1 contrast ratio (AUD-017): the design page computes these instead of hard-coding badges.
 */

function channel(c: number): number {
  const s = c / 255
  return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
}

export function relativeLuminance(hex: string): number {
  const h = hex.replace('#', '')
  if (!/^[0-9a-fA-F]{6}$/.test(h)) throw new Error(`Expected #RRGGBB, got ${hex}`)
  const r = parseInt(h.slice(0, 2), 16)
  const g = parseInt(h.slice(2, 4), 16)
  const b = parseInt(h.slice(4, 6), 16)
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
}

export function contrastRatio(foreground: string, background: string): number {
  const a = relativeLuminance(foreground)
  const b = relativeLuminance(background)
  const [hi, lo] = a >= b ? [a, b] : [b, a]
  return (hi + 0.05) / (lo + 0.05)
}

/** AA thresholds: 4.5:1 normal text, 3:1 large text / UI components. */
export function meetsAA(ratio: number, kind: 'text' | 'large-or-ui' = 'text'): boolean {
  return ratio >= (kind === 'text' ? 4.5 : 3)
}

export function formatRatio(ratio: number): string {
  return `${ratio.toFixed(1)}:1`
}
