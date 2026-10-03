// @vitest-environment jsdom
import '../../test/setupDom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { createFakePdf, deferred } from '../../test/fakePdf'

const pdf = vi.hoisted(() => ({ current: null as unknown }))

vi.mock('../../lib/pdf/renderer', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/pdf/renderer')>()
  return { ...actual, loadPdf: vi.fn(async () => pdf.current) }
})

import AuditTrailView from './AuditTrailView'

function jsonResponse(body: unknown, ok = true, status = 200): Response {
  return { ok, status, json: async () => body } as Response
}

describe('AuditTrailView PDF render race (AUD-001)', () => {
  const originalFetch = globalThis.fetch
  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
  })
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  it('renders the component page when the PDF loads before the provenance chain', async () => {
    const { doc, stats } = createFakePdf(3, 40)
    pdf.current = doc
    const provenance = deferred<Response>()
    vi.mocked(fetch).mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/provenance')) return provenance.promise
      if (url.includes('/audit-trail/')) {
        return jsonResponse({
          job_id: 'job-race',
          sheet_name: 'Reconciliation',
          cell_coord: 'B4',
          provenance_id: 'p1',
          node_id: 'n1',
          is_formula: false,
          formula_expression: null,
          is_found: true,
          error_detail: null,
          components: [
            {
              component_id: 'c1',
              source_file: 'filing.pdf',
              page: 2,
              bbox: { x0: 100, y0: 100, x1: 200, y1: 120 },
              value: '1,000',
              label: 'Net income',
              normalized_label: 'Net Income',
              review_status: 'locked',
              is_missing: false,
              provenance_id: 'p1',
            },
          ],
        })
      }
      return jsonResponse({}, false, 404)
    })

    render(<AuditTrailView jobId="job-race" apiBase="http://api" onBack={() => {}} />)

    await waitFor(() => expect(stats.renderCalls.length).toBeGreaterThan(0))
    await act(async () => {
      provenance.resolve(
        jsonResponse({
          job_id: 'job-race',
          total_records: 1,
          records: [{ id: 'p1', job_id: 'job-race', sheet_name: 'Reconciliation', cell_coord: 'B4', node_id: 'n1', is_formula: false }],
        }),
      )
    })

    await waitFor(() => expect(stats.completedRenders).toContain(2), { timeout: 2000 })
    expect(stats.canvasConflicts).toBe(0)
    expect(screen.queryByText(/Cannot use the same canvas/i)).toBeNull()
  })
})
