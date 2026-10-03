// @vitest-environment jsdom
import '../test/setupDom'
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import App from '../App'

describe('API base comes from VITE_API_BASE (AUD-034, D9)', () => {
  const originalFetch = globalThis.fetch
  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.unstubAllEnvs()
    vi.restoreAllMocks()
  })

  it('calls the configured backend instead of localhost:8000', async () => {
    vi.stubEnv('VITE_API_BASE', 'https://api.example.test/')
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      const body = url.endsWith('/upload/jobs') ? { jobs: [] } : url.endsWith('/health') ? { status: 'ok' } : []
      return { ok: true, status: 200, json: async () => body } as Response
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const urls = fetchMock.mock.calls.map((c) => String(c[0]))
    expect(urls).toContain('https://api.example.test/upload/jobs')
    expect(urls.filter((u) => u.includes('localhost:8000'))).toEqual([])
  })
})
