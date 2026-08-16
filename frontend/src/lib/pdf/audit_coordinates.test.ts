import { describe, it, expect } from 'vitest'
import { normalizeBboxToPixels } from './coordinates'
import type { BoundingBox, SourceComponent, SourceChainResponse } from '../../types/audit'

describe('Audit Trail Coordinate & Data Model Handling', () => {
  it('correctly projects 0-1000 normalized bbox to canvas dimensions (AC-3)', () => {
    const bbox: BoundingBox = {
      x0: 100, // 10%
      y0: 200, // 20%
      x1: 400, // 40%
      y1: 300, // 30%
    }
    const pageWidth = 800
    const pageHeight = 1000

    const pixels = normalizeBboxToPixels(bbox, pageWidth, pageHeight)

    expect(pixels.left).toBe(80)    // 10% of 800
    expect(pixels.top).toBe(200)   // 20% of 1000
    expect(pixels.width).toBe(240) // 30% of 800
    expect(pixels.height).toBe(100)// 10% of 1000
  })

  it('clamps out-of-bounds bbox coordinates to canvas boundary without overflow (AC-3)', () => {
    const bbox: BoundingBox = {
      x0: -50,
      y0: -20,
      x1: 1200,
      y1: 1100,
    }
    const pageWidth = 1000
    const pageHeight = 1000

    const pixels = normalizeBboxToPixels(bbox, pageWidth, pageHeight)

    expect(pixels.left).toBe(0)
    expect(pixels.top).toBe(0)
    expect(pixels.width).toBe(1000)
    expect(pixels.height).toBe(1000)
  })

  it('structures multi-component aggregated source chain properly (AC-2)', () => {
    const components: SourceComponent[] = [
      {
        component_id: 'job123_0',
        source_file: 'filing_2023.pdf',
        page: 14,
        bbox: { x0: 100, y0: 150, x1: 300, y1: 180 },
        value: '250.00',
        label: 'Stock-based comp R&D',
        normalized_label: 'Stock-Based Compensation',
        review_status: 'flagged',
        is_missing: false,
        provenance_id: 'urn:footnote:provenance:job123:Source_Inputs:F2',
      },
      {
        component_id: 'job123_1',
        source_file: 'filing_2023.pdf',
        page: 18,
        bbox: { x0: 110, y0: 220, x1: 320, y1: 250 },
        value: '150.00',
        label: 'Stock-based comp SG&A',
        normalized_label: 'Stock-Based Compensation',
        review_status: 'locked',
        is_missing: false,
        provenance_id: 'urn:footnote:provenance:job123:Source_Inputs:F3',
      },
    ]

    const response: SourceChainResponse = {
      job_id: 'job123',
      sheet_name: 'Reconciliation',
      cell_coord: 'C7',
      provenance_id: 'urn:footnote:provenance:job123:Reconciliation:C7',
      node_id: 'agg_stockbased_compensation',
      is_formula: true,
      formula_expression: '=SUM(Source_Inputs!F2, Source_Inputs!F3)',
      is_found: true,
      components,
      error_detail: null,
    }

    expect(response.is_found).toBe(true)
    expect(response.components.length).toBe(2)
    expect(response.components[0].page).toBe(14)
    expect(response.components[0].review_status).toBe('flagged')
    expect(response.components[1].page).toBe(18)
    expect(response.components[1].review_status).toBe('locked')
  })
})
