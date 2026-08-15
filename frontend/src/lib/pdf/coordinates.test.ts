import { describe, it, expect } from 'vitest'
import { normalizeBboxToPixels } from './coordinates'

describe('normalizeBboxToPixels', () => {
  it('correctly scales 0-1000 coordinates to canvas pixels (spec AC-3)', () => {
    const bbox = { x0: 100, y0: 200, x1: 300, y1: 250 }
    const pageWidth = 800
    const pageHeight = 1000

    const result = normalizeBboxToPixels(bbox, pageWidth, pageHeight)

    expect(result.left).toBe(80) // (100 / 1000) * 800
    expect(result.top).toBe(200) // (200 / 1000) * 1000
    expect(result.width).toBe(160) // ((300 - 100) / 1000) * 800
    expect(result.height).toBe(50) // ((250 - 200) / 1000) * 1000
  })

  it('clamps coordinates exceeding 0-1000 boundary', () => {
    const bbox = { x0: -50, y0: 0, x1: 1050, y1: 1000 }
    const pageWidth = 1000
    const pageHeight = 1000

    const result = normalizeBboxToPixels(bbox, pageWidth, pageHeight)

    expect(result.left).toBe(0)
    expect(result.top).toBe(0)
    expect(result.width).toBe(1000)
    expect(result.height).toBe(1000)
  })

  it('handles inverted coordinates (x0 > x1 or y0 > y1)', () => {
    const bbox = { x0: 400, y0: 300, x1: 200, y1: 100 }
    const pageWidth = 500
    const pageHeight = 1000

    const result = normalizeBboxToPixels(bbox, pageWidth, pageHeight)

    expect(result.left).toBe(100) // min(200, 400) -> 200/1000 * 500
    expect(result.top).toBe(100) // min(100, 300) -> 100/1000 * 1000
    expect(result.width).toBe(100) // (400 - 200)/1000 * 500
    expect(result.height).toBe(200) // (300 - 100)/1000 * 1000
  })

  it('handles zero or negative page dimensions gracefully', () => {
    const bbox = { x0: 100, y0: 100, x1: 200, y1: 200 }
    expect(normalizeBboxToPixels(bbox, 0, 1000)).toEqual({ left: 0, top: 0, width: 0, height: 0 })
    expect(normalizeBboxToPixels(bbox, 800, -10)).toEqual({ left: 0, top: 0, width: 0, height: 0 })
  })

  it('handles duplicate bbox coordinates (EC-3)', () => {
    const bbox1 = { x0: 150, y0: 250, x1: 350, y1: 300 }
    const bbox2 = { x0: 150, y0: 250, x1: 350, y1: 300 }
    const pageWidth = 1000
    const pageHeight = 1000

    const res1 = normalizeBboxToPixels(bbox1, pageWidth, pageHeight)
    const res2 = normalizeBboxToPixels(bbox2, pageWidth, pageHeight)

    expect(res1).toEqual(res2)
    expect(res1.left).toBe(150)
    expect(res1.top).toBe(250)
  })
})
