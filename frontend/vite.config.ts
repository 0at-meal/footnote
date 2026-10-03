/// <reference types="vitest" />
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    // Default environment is node; DOM component tests opt in with
    // `// @vitest-environment jsdom` (see src/test/setupDom.ts).
    environment: 'node',
    // Playwright specs live in e2e/ and run with `npm run e2e`.
    exclude: ['**/node_modules/**', '**/dist/**', 'e2e/**'],
  },
})
