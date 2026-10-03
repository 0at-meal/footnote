/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend origin for API calls (AUD-034). Defaults to http://localhost:8000. */
  readonly VITE_API_BASE?: string
}
