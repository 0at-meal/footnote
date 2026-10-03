// @vitest-environment jsdom
import '../test/setupDom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import App from '../App'
import JobList from './JobList'
import type { JobRecord } from '../types/job'

function jsonResponse(body: unknown, ok = true, status = 200): Response {
  return { ok, status, json: async () => body } as Response
}

const REASON =
  "Docling is not installed in this Python interpreter (ModuleNotFoundError: No module named 'docling'). PDF extraction uses the PyMuPDF fallback."

describe('Degraded parser mode is visible (AUD-003, D1)', () => {
  const originalFetch = globalThis.fetch
  beforeEach(() => vi.stubGlobal('fetch', vi.fn()))
  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
  })

  it('shows a persistent banner with the reason when /health reports degraded', async () => {
    vi.mocked(fetch).mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/health')) {
        return jsonResponse({ status: 'degraded', docling_available: false, parser_mode: 'pymupdf_fallback', degraded_reason: REASON })
      }
      if (url.endsWith('/upload/jobs')) return jsonResponse({ jobs: [] })
      return jsonResponse([])
    })
    render(<App />)
    const banner = await screen.findByRole('alert', { name: /degraded/i })
    expect(within(banner).getByText(/PyMuPDF fallback/)).toBeTruthy()
  })

  it('stamps a job row with the parser fallback reason and a failed job with its failure reason', () => {
    const jobs: JobRecord[] = [
      {
        job_id: 'j1',
        filename: 'fallback.pdf',
        file_size_bytes: 10,
        status: 'done',
        target_metric: 'Adjusted EBITDA',
        submitted_at: '2026-10-03T00:00:00Z',
        parser_used: 'pymupdf',
        parser_fallback_reason: 'Docling unavailable (ModuleNotFoundError); used PyMuPDF fallback.',
      },
      {
        job_id: 'j2',
        filename: 'broken.pdf',
        file_size_bytes: 10,
        status: 'failed',
        target_metric: 'Adjusted EBITDA',
        submitted_at: '2026-10-03T00:00:00Z',
        failure_reason: 'DoclingParseError: Docling is not installed in this Python interpreter',
      },
    ]
    render(<JobList stagedFiles={[]} persistedJobs={jobs} onRemove={() => {}} />)
    expect(screen.getByText(/Docling unavailable \(ModuleNotFoundError\)/)).toBeTruthy()
    expect(screen.getByText(/DoclingParseError: Docling is not installed/)).toBeTruthy()
  })
})
