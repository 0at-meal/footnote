/**
 * Test double for a pdf.js PDFDocumentProxy (dependency of the unit under test, not the unit itself).
 *
 * It reproduces the pdf.js 4.10 rule that matters for the review viewer:
 * a second `page.render()` on a canvas that is still being rendered rejects with
 * "Cannot use the same canvas during multiple render() operations" (pdf.mjs #canvasInUse).
 * Cancelling a task rejects it with a RenderingCancelledException and frees the canvas.
 */
import type { PDFDocumentProxy } from '../lib/pdf/renderer'

export interface FakePdfStats {
  renderCalls: number[]
  completedRenders: number[]
  canvasConflicts: number
  cancelled: number
}

export function createFakePdf(numPages: number, renderMs = 30): { doc: PDFDocumentProxy; stats: FakePdfStats } {
  const inUse = new WeakSet<object>()
  const stats: FakePdfStats = { renderCalls: [], completedRenders: [], canvasConflicts: 0, cancelled: 0 }

  const doc = {
    numPages,
    async getPage(pageNumber: number) {
      return {
        getViewport({ scale }: { scale: number }) {
          return { width: 600 * scale, height: 800 * scale, scale }
        },
        render({ canvasContext }: { canvasContext: { canvas: object } }) {
          stats.renderCalls.push(pageNumber)
          const canvas = canvasContext.canvas
          let cancelFn: () => void = () => {}
          const promise = new Promise<void>((resolve, reject) => {
            if (inUse.has(canvas)) {
              stats.canvasConflicts += 1
              reject(
                new Error(
                  'Cannot use the same canvas during multiple render() operations. Use different canvas or ensure previous operations were cancelled or completed.',
                ),
              )
              return
            }
            inUse.add(canvas)
            const timer = setTimeout(() => {
              inUse.delete(canvas)
              stats.completedRenders.push(pageNumber)
              resolve()
            }, renderMs)
            cancelFn = () => {
              clearTimeout(timer)
              inUse.delete(canvas)
              stats.cancelled += 1
              const err = new Error('Rendering cancelled, page ' + pageNumber)
              err.name = 'RenderingCancelledException'
              reject(err)
            }
          })
          return { promise, cancel: () => cancelFn() }
        },
      }
    },
  }
  return { doc: doc as unknown as PDFDocumentProxy, stats }
}

export function deferred<T>(): { promise: Promise<T>; resolve: (v: T) => void } {
  let resolve!: (v: T) => void
  const promise = new Promise<T>((r) => {
    resolve = r
  })
  return { promise, resolve }
}
