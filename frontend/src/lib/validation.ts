/**
 * Client-side PDF validation.
 *
 * Scope: MIME type and extension checks only.
 * Magic-byte validation (catches renamed non-PDFs, corrupted files,
 * password-protected PDFs) is server-side — Feature 1, Step 2.
 */

/**
 * Returns true if the File is a PDF by MIME type.
 * Falls back to extension when the browser leaves File.type empty,
 * which can happen with drag-and-drop on some OS / browser combinations.
 */
export function isPdf(file: File): boolean {
  if (file.type !== '') return file.type === 'application/pdf'
  return file.name.toLowerCase().endsWith('.pdf')
}
