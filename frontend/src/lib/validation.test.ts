import { describe, it, expect } from 'vitest'
import { isPdf } from './validation'

/**
 * Unit tests for isPdf().
 *
 * This function is the client-side gate that decides which files enter
 * the staged-file list. Getting it wrong means either blocking valid PDFs
 * or letting non-PDFs through to the server — both are user-visible failures.
 *
 * Coverage targets:
 *   - MIME type present and correct  → accept
 *   - MIME type present and wrong    → reject
 *   - MIME type absent + .pdf ext   → accept (drag-and-drop fallback)
 *   - MIME type absent + other ext  → reject
 *   - MIME type correct + wrong ext → MIME wins (accept)
 *   - MIME type wrong  + .pdf ext   → MIME wins (reject)
 */

function makeFile(name: string, type: string): File {
  return new File([], name, { type })
}

describe('isPdf', () => {
  describe('when MIME type is set (primary path)', () => {
    it('accepts a file with type application/pdf', () => {
      expect(isPdf(makeFile('report.pdf', 'application/pdf'))).toBe(true)
    })

    it('rejects a file with type image/jpeg', () => {
      expect(isPdf(makeFile('photo.jpg', 'image/jpeg'))).toBe(false)
    })

    it('rejects a file with type application/msword', () => {
      expect(isPdf(makeFile('document.docx', 'application/msword'))).toBe(false)
    })

    it('rejects a file with type application/vnd.ms-excel', () => {
      expect(isPdf(makeFile('model.xlsx', 'application/vnd.ms-excel'))).toBe(false)
    })

    it('rejects a file with type text/plain', () => {
      expect(isPdf(makeFile('notes.txt', 'text/plain'))).toBe(false)
    })

    it('rejects a file with type image/png', () => {
      expect(isPdf(makeFile('chart.png', 'image/png'))).toBe(false)
    })

    // MIME wins even when extension disagrees
    it('accepts a file whose MIME is pdf but extension is not .pdf', () => {
      expect(isPdf(makeFile('renamed', 'application/pdf'))).toBe(true)
    })

    it('rejects a file whose MIME is wrong even if extension is .pdf', () => {
      expect(isPdf(makeFile('disguised.pdf', 'image/jpeg'))).toBe(false)
    })
  })

  describe('when MIME type is empty (drag-and-drop fallback path)', () => {
    it('accepts a file with .pdf extension when type is empty', () => {
      expect(isPdf(makeFile('annual_report.pdf', ''))).toBe(true)
    })

    it('accepts a .pdf file with uppercase extension when type is empty', () => {
      expect(isPdf(makeFile('FILING.PDF', ''))).toBe(true)
    })

    it('accepts a .pdf file with mixed-case extension when type is empty', () => {
      expect(isPdf(makeFile('Filing.Pdf', ''))).toBe(true)
    })

    it('rejects a .docx file when type is empty', () => {
      expect(isPdf(makeFile('resume.docx', ''))).toBe(false)
    })

    it('rejects a .png file when type is empty', () => {
      expect(isPdf(makeFile('screenshot.png', ''))).toBe(false)
    })

    it('rejects a file with no extension when type is empty', () => {
      expect(isPdf(makeFile('unknownfile', ''))).toBe(false)
    })

    it('rejects a file whose name contains .pdf but does not end with it', () => {
      // e.g. "report.pdf.jpg" — endsWith check must be exact
      expect(isPdf(makeFile('report.pdf.jpg', ''))).toBe(false)
    })
  })
})
