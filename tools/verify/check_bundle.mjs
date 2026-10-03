#!/usr/bin/env node
/**
 * Fails if the production bundle contains dev-only design scaffolding or mock copy (AUD-017, D7).
 *
 * Usage (after `npm --prefix frontend run build`):
 *   node tools/verify/check_bundle.mjs [distDir]
 * or `npm --prefix frontend run verify:bundle` (builds first).
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const distDir = resolve(process.argv[2] ?? join(here, '..', '..', 'frontend', 'dist'))

const FORBIDDEN = [
  'Design System',
  'Exit Design',
  'Specification-compliant primitives',
  'Single-User',
  'Auto-detects company',
  'Output Preview',
  'Total Debt $2.5B',
]

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name)
    return statSync(p).isDirectory() ? walk(p) : [p]
  })
}

let files
try {
  files = walk(distDir).filter((p) => /\.(js|mjs|css|html)$/.test(p))
} catch (err) {
  console.error(`Cannot read ${distDir}: ${err.message}. Run the production build first.`)
  process.exit(2)
}

const hits = []
for (const file of files) {
  const text = readFileSync(file, 'utf8')
  for (const needle of FORBIDDEN) {
    if (text.includes(needle)) hits.push(`${needle}  <-  ${file}`)
  }
}

if (hits.length) {
  console.error(`FAIL: production bundle contains dev-only/mock strings (${hits.length}):`)
  for (const h of hits) console.error(`  ${h}`)
  process.exit(1)
}
console.log(`OK: ${files.length} bundle files, none contain: ${FORBIDDEN.join(' | ')}`)
