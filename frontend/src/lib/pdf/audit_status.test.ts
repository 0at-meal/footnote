import { describe, it, expect } from 'vitest'
import type { SourceComponent } from '../../types/audit'
import { computeChainRollup } from './audit_status'

describe('Audit Trail Review Status Rollup (Feature 6 Step 3)', () => {
  it('identifies when all contributing components are verified & locked (AC-4)', () => {
    const components: SourceComponent[] = [
      {
        component_id: 'c1',
        source_file: '10k.pdf',
        page: 12,
        bbox: { x0: 100, y0: 100, x1: 200, y1: 200 },
        value: '100',
        label: 'Op Inc',
        normalized_label: 'Operating Income',
        review_status: 'locked',
        is_missing: false,
        provenance_id: null,
      },
      {
        component_id: 'c2',
        source_file: '10k.pdf',
        page: 14,
        bbox: { x0: 100, y0: 100, x1: 200, y1: 200 },
        value: '200',
        label: 'SBC',
        normalized_label: 'Stock-Based Compensation',
        review_status: 'locked',
        is_missing: false,
        provenance_id: null,
      },
    ]

    const rollup = computeChainRollup(components)
    expect(rollup.kind).toBe('all_locked')
    expect(rollup.label).toBe('All Verified (2/2)')
    expect(rollup.badgeClass).toBe('status-badge--done')
  })

  it('highlights flagged components with high-priority warning (AC-4, EC-5)', () => {
    const components: SourceComponent[] = [
      {
        component_id: 'c1',
        source_file: '10k.pdf',
        page: 12,
        bbox: { x0: 100, y0: 100, x1: 200, y1: 200 },
        value: '100',
        label: 'Op Inc',
        normalized_label: 'Operating Income',
        review_status: 'locked',
        is_missing: false,
        provenance_id: null,
      },
      {
        component_id: 'c2',
        source_file: '10k.pdf',
        page: 14,
        bbox: { x0: 100, y0: 100, x1: 200, y1: 200 },
        value: '200',
        label: 'SBC',
        normalized_label: 'Stock-Based Compensation',
        review_status: 'flagged',
        is_missing: false,
        provenance_id: null,
      },
    ]

    const rollup = computeChainRollup(components)
    expect(rollup.kind).toBe('contains_flagged')
    expect(rollup.label).toBe('Flagged (1/2)')
    expect(rollup.badgeClass).toBe('status-badge--extracting')
  })

  it('surfaces missing record gaps (EC-1)', () => {
    const components: SourceComponent[] = [
      {
        component_id: 'c1',
        source_file: '10k.pdf',
        page: 12,
        bbox: { x0: 100, y0: 100, x1: 200, y1: 200 },
        value: '100',
        label: 'Op Inc',
        normalized_label: 'Operating Income',
        review_status: 'source_record_missing',
        is_missing: true,
        provenance_id: null,
      },
    ]

    const rollup = computeChainRollup(components)
    expect(rollup.kind).toBe('has_missing')
    expect(rollup.label).toBe('Missing Records (1/1)')
    expect(rollup.badgeClass).toBe('status-badge--failed')
  })
})
