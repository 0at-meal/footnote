/**
 * sec.gov links for items from SEC HTML filings (AUD-018, decision D9).
 *
 * Only CIK-qualified EDGAR Archives URLs are used; the CIK-less forms return 404 or redirect.
 * Mirrors backend `app/extraction/locator.py::sec_archives_url`.
 */
import type { HtmlLocator } from '../types/review'

const ARCHIVES = /^https:\/\/www\.sec\.gov\/Archives\/edgar\/data\/[1-9]\d*\/\d{18}\/[^/#?]+$/

/** Text-fragment encoding: `&`, `,` and `-` are syntax inside `#:~:text=` and must be escaped. */
function encodeTextFragment(text: string): string {
  return encodeURIComponent(text).replace(/-/g, '%2D')
}

function archivesUrl(locator: HtmlLocator): string | null {
  const stored = (locator.url ?? '').split('#')[0]
  if (ARCHIVES.test(stored)) return stored
  const cik = Number.parseInt(locator.cik ?? '', 10)
  const acc = (locator.accession ?? '').replace(/-/g, '')
  if (!Number.isFinite(cik) || cik <= 0 || !/^\d{18}$/.test(acc) || !locator.document) return null
  return `https://www.sec.gov/Archives/edgar/data/${cik}/${acc}/${encodeURIComponent(locator.document)}`
}

/**
 * Link to the filing on sec.gov, scrolled to the item's row label, or null when no valid URL
 * can be built (the UI then says so instead of offering a broken link).
 */
export function secSourceLink(locator: HtmlLocator, label: string): string | null {
  const url = archivesUrl(locator)
  if (!url) return null
  const row = label.split(' > ').pop()?.trim()
  return row ? `${url}#:~:text=${encodeTextFragment(row)}` : url
}
