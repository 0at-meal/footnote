/**
 * PDF.js rendering utility for Footnote Extraction Review (Feature 5).
 *
 * Enforces CONSTITUTION §3.7:
 * - lib/pdf/ may ONLY talk to components/review/.
 * - Bundles pdfjs-dist worker locally via Vite asset URL to avoid remote CDN calls (§6.5).
 */

import * as pdfjsLib from 'pdfjs-dist'
import type { PDFDocumentProxy, PDFPageProxy, RenderTask } from 'pdfjs-dist'
import pdfWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

if (typeof window !== 'undefined' && pdfjsLib.GlobalWorkerOptions) {
  pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorker
}

export const PDF_RENDER_SCALE = 1.5

export type { PDFDocumentProxy, PDFPageProxy }

/**
 * Loads a PDF document from a streaming URL endpoint.
 *
 * @param url Stream URL (e.g. http://localhost:8000/review/{job_id}/pdf)
 * @returns PDFDocumentProxy instance
 */
export async function loadPdf(url: string): Promise<PDFDocumentProxy> {
  const loadingTask = pdfjsLib.getDocument({
    url,
  })
  return await loadingTask.promise
}

/**
 * Renders a 1-indexed page from a loaded PDFDocumentProxy to an HTML5 canvas.
 *
 * @param doc Loaded PDF document
 * @param pageNumber 1-indexed page number to render
 * @param canvas Target HTMLCanvasElement
 * @param scale Zoom scale factor (default: 1.5)
 */
export async function renderPage(
  doc: PDFDocumentProxy,
  pageNumber: number,
  canvas: HTMLCanvasElement,
  scale: number = 1.5,
): Promise<void> {
  if (pageNumber < 1 || pageNumber > doc.numPages) {
    throw new Error(`Page ${pageNumber} not found in document (total pages: ${doc.numPages})`)
  }

  const page = await doc.getPage(pageNumber)
  const viewport = page.getViewport({ scale })

  const dpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1
  canvas.width = Math.floor(viewport.width * dpr)
  canvas.height = Math.floor(viewport.height * dpr)
  canvas.style.width = `${Math.floor(viewport.width)}px`
  canvas.style.height = `${Math.floor(viewport.height)}px`

  const ctx = canvas.getContext('2d')
  if (!ctx) {
    throw new Error('Failed to get 2D canvas rendering context')
  }

  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

  const renderContext = {
    canvasContext: ctx,
    viewport: viewport,
  }

  const renderTask: RenderTask = page.render(renderContext)
  await renderTask.promise
}

export type SerialRenderResult = 'rendered' | 'superseded'

export interface SerialPageRenderer {
  /**
   * Render `pageNumber` into `canvas`. Any render still in flight on this renderer is
   * cancelled and awaited first, so pdf.js never sees two concurrent renders on one canvas.
   * Resolves 'superseded' when a newer render request replaced this one.
   */
  render(doc: PDFDocumentProxy, pageNumber: number, canvas: HTMLCanvasElement, scale: number): Promise<SerialRenderResult>
  /** Cancel whatever is in flight (call on unmount). */
  cancel(): void
}

function isCancellation(err: unknown): boolean {
  return err instanceof Error && err.name === 'RenderingCancelledException'
}

/**
 * One renderer per canvas (AUD-001). pdf.js 4.x rejects a second `page.render()` on a canvas
 * that is still rendering ("Cannot use the same canvas during multiple render() operations").
 * The previous implementation let React effects start overlapping renders; this serializes them.
 */
export function createSerialRenderer(): SerialPageRenderer {
  let generation = 0
  let inFlight: { task: RenderTask; settled: Promise<void> } | null = null

  async function render(
    doc: PDFDocumentProxy,
    pageNumber: number,
    canvas: HTMLCanvasElement,
    scale: number,
  ): Promise<SerialRenderResult> {
    const myGeneration = ++generation
    if (inFlight) {
      inFlight.task.cancel()
      await inFlight.settled
    }
    if (myGeneration !== generation) return 'superseded'

    if (pageNumber < 1 || pageNumber > doc.numPages) {
      throw new Error(`Page ${pageNumber} not found in document (total pages: ${doc.numPages})`)
    }
    const page = await doc.getPage(pageNumber)
    if (myGeneration !== generation) return 'superseded'
    // A newer request may have started a task while getPage was pending.
    if (inFlight) {
      inFlight.task.cancel()
      await inFlight.settled
      if (myGeneration !== generation) return 'superseded'
    }

    const viewport = page.getViewport({ scale })
    const dpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1
    canvas.width = Math.floor(viewport.width * dpr)
    canvas.height = Math.floor(viewport.height * dpr)
    canvas.style.width = `${Math.floor(viewport.width)}px`
    canvas.style.height = `${Math.floor(viewport.height)}px`
    const ctx = canvas.getContext('2d')
    if (!ctx) {
      throw new Error('Failed to get 2D canvas rendering context')
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

    const task: RenderTask = page.render({ canvasContext: ctx, viewport })
    const settled = task.promise.then(
      () => undefined,
      () => undefined,
    )
    inFlight = { task, settled }
    try {
      await task.promise
    } catch (err) {
      if (isCancellation(err) || myGeneration !== generation) return 'superseded'
      throw err
    } finally {
      if (inFlight?.task === task) inFlight = null
    }
    return myGeneration === generation ? 'rendered' : 'superseded'
  }

  function cancel(): void {
    generation += 1
    inFlight?.task.cancel()
  }

  return { render, cancel }
}
