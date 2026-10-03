/**
 * Runtime configuration (AUD-034, D9).
 *
 * VITE_API_BASE: backend origin, e.g. https://api.footnote.example. Defaults to the local
 * dev backend. Read at call time so tests (vi.stubEnv) and builds both see the right value.
 */
export function getApiBase(): string {
  const configured = (import.meta.env.VITE_API_BASE as string | undefined)?.trim()
  return (configured || 'http://localhost:8000').replace(/\/+$/, '')
}
