// @vitest-environment jsdom
import '../test/setupDom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import App from '../App'
import UploadZone from './UploadZone'
import { AppShell } from './shell/AppShell'
import { DesignPreviewPage } from './design/DesignPreviewPage'

function jsonResponse(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as Response
}

describe('Production surface has no design scaffolding or mock content (AUD-017, D7)', () => {
  const originalFetch = globalThis.fetch
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/health')) return jsonResponse({ status: 'ok' })
      if (url.endsWith('/upload/jobs')) return jsonResponse({ jobs: [] })
      return jsonResponse([])
    }))
  })
  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.unstubAllEnvs()
    vi.restoreAllMocks()
    window.history.pushState(null, '', '/')
  })

  it('outside dev builds there is no /design button and /design renders the app', async () => {
    vi.stubEnv('DEV', false)
    window.history.pushState(null, '', '/design')
    render(<App />)
    expect(await screen.findByText(/What do you want to build/i)).toBeTruthy()
    expect(screen.queryByRole('button', { name: /\/design|exit design/i })).toBeNull()
    expect(screen.queryByText(/Design System/i)).toBeNull()
  })

  it('in dev builds the design route is still reachable', async () => {
    vi.stubEnv('DEV', true)
    window.history.pushState(null, '', '/design')
    render(<App />)
    expect(await screen.findByText(/Specification-compliant primitives/i, {}, { timeout: 3000 })).toBeTruthy()
  })

  it('defaults to the light theme when no preference is saved', () => {
    render(<AppShell>content</AppShell>)
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })

  it('shows no environment badge in the shell', () => {
    render(<AppShell>content</AppShell>)
    expect(screen.queryByText(/Single-User/i)).toBeNull()
  })

  it('pack cards show no mock output and the upload bar makes no auto-detection claim', () => {
    render(<UploadZone onFilesAdded={() => {}} />)
    expect(screen.queryByText(/Output Preview/i)).toBeNull()
    expect(screen.queryByText(/Total Debt \$2\.5B/)).toBeNull()
    expect(screen.queryByText(/5\.25% Senior Notes/)).toBeNull()
    expect(screen.queryByText(/Auto-detects/i)).toBeNull()
  })

  it('design page contrast figures are computed, not hard-coded', () => {
    render(<DesignPreviewPage />)
    // Real WCAG ratios of the documented token pairs (computed independently in contrast.test.ts).
    fireEvent.click(screen.getByRole('tab', { name: /Contrast/i }))
    expect(screen.queryByText(/14\.2:1/)).toBeNull()
    expect(screen.getAllByText(/17\.6:1/).length).toBeGreaterThan(0)
  })
})
