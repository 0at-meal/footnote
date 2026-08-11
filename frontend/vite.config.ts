/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    // File constructor is available natively in Node 20+ — no jsdom needed
    // for the current test suite (pure function tests only).
    environment: 'node',
  },
})
