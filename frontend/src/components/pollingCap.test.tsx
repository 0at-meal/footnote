// @vitest-environment jsdom
import '../test/setupDom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import App from '../App'

function jsonResponse(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as Response
}

describe('Queue polling is bounded (AUD-035)', () => {
  const originalFetch = globalThis.fetch
  let jobPolls = 0

  beforeEach(() => {
    jobPolls = 0
    vi.useFakeTimers()
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.endsWith('/health')) return jsonResponse({ status: 'ok' })
        if (url.endsWith('/upload/jobs')) {
          jobPolls += 1
          return jsonResponse({
            jobs: [
              {
                job_id: 'z1',
                filename: 'never_finishes.pdf',
                file_size_bytes: 1,
                status: 'extracting',
                target_metric: 'Adjusted EBITDA',
                submitted_at: '2026-10-03T00:00:00Z',
              },
            ],
          })
        }
        return jsonResponse([])
      }),
    )
  })
  afterEach(() => {
    vi.useRealTimers()
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
  })

  it('stops polling a job that never leaves extracting and tells the user', async () => {
    render(<App />)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000) // initial load
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(21 * 60 * 1000)
    })
    expect(jobPolls).toBeGreaterThan(10) // it did poll while the job was active
    const pollsAt21 = jobPolls
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10 * 60 * 1000)
    })
    expect(jobPolls).toBe(pollsAt21)
    expect(screen.getByText(/Auto-refresh paused/i)).toBeTruthy()
  })
})
