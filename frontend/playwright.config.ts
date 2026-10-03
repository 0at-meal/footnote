/**
 * Playwright e2e config. Starts the real backend (venv interpreter, isolated FOOTNOTE_DATA_DIR
 * seeded by tools/verify/seed_e2e.py) and the Vite dev server. Never touches backend/data.
 *
 *   npx playwright test            (uses bundled Chromium if installed, else local Chrome)
 */
import { defineConfig, chromium } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const PY =
  process.platform === 'win32' ? join(ROOT, '.venv', 'Scripts', 'python.exe') : join(ROOT, '.venv', 'bin', 'python')

if (!process.env.FN_E2E_DATA_DIR) {
  const dir = mkdtempSync(join(tmpdir(), 'footnote-e2e-'))
  execFileSync(PY, [join(ROOT, 'tools', 'verify', 'seed_e2e.py'), '--data-dir', dir], {
    stdio: 'inherit',
    env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' },
  })
  process.env.FN_E2E_DATA_DIR = dir
}

let channel = process.env.PW_CHANNEL || undefined
if (!channel) {
  try {
    if (!existsSync(chromium.executablePath())) channel = 'chrome'
  } catch {
    channel = 'chrome'
  }
}

export default defineConfig({
  testDir: './e2e',
  timeout: 180_000,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:5173',
    channel,
    viewport: { width: 1280, height: 800 },
  },
  webServer: [
    {
      command: `"${PY}" "${join(ROOT, 'tools', 'run_backend.py')}" --host 127.0.0.1 --port 8000`,
      url: 'http://127.0.0.1:8000/health',
      reuseExistingServer: false,
      timeout: 240_000,
      env: { FOOTNOTE_DATA_DIR: process.env.FN_E2E_DATA_DIR as string, PYTHONDONTWRITEBYTECODE: '1' },
    },
    {
      command: 'npx vite --port 5173 --strictPort',
      url: 'http://localhost:5173',
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
})
