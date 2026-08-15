import { describe, it, expect, vi } from 'vitest'
import { renderPage } from './renderer'
import type { PDFDocumentProxy, PDFPageProxy } from './renderer'

function createMockCanvas(): HTMLCanvasElement {
  const ctx = {
    setTransform: vi.fn(),
  }
  return {
    width: 0,
    height: 0,
    style: {} as CSSStyleDeclaration,
    getContext: vi.fn().mockReturnValue(ctx),
  } as unknown as HTMLCanvasElement
}

describe('renderPage', () => {
  it('throws an error if pageNumber is less than 1 (EC-2)', async () => {
    const mockDoc = {
      numPages: 5,
      getPage: vi.fn(),
    } as unknown as PDFDocumentProxy

    const canvas = createMockCanvas()

    await expect(renderPage(mockDoc, 0, canvas)).rejects.toThrow(
      'Page 0 not found in document (total pages: 5)',
    )
  })

  it('throws an error if pageNumber exceeds doc.numPages (EC-2)', async () => {
    const mockDoc = {
      numPages: 5,
      getPage: vi.fn(),
    } as unknown as PDFDocumentProxy

    const canvas = createMockCanvas()

    await expect(renderPage(mockDoc, 6, canvas)).rejects.toThrow(
      'Page 6 not found in document (total pages: 5)',
    )
  })

  it('renders page to canvas successfully when pageNumber is valid', async () => {
    const mockRenderPromise = Promise.resolve()
    const mockPage = {
      getViewport: vi.fn().mockReturnValue({ width: 800, height: 1000 }),
      render: vi.fn().mockReturnValue({ promise: mockRenderPromise }),
    } as unknown as PDFPageProxy

    const mockDoc = {
      numPages: 10,
      getPage: vi.fn().mockResolvedValue(mockPage),
    } as unknown as PDFDocumentProxy

    const canvas = createMockCanvas()

    await renderPage(mockDoc, 3, canvas, 1.5)

    expect(mockDoc.getPage).toHaveBeenCalledWith(3)
    expect(mockPage.getViewport).toHaveBeenCalledWith({ scale: 1.5 })
    expect(mockPage.render).toHaveBeenCalled()
    expect(canvas.style.width).toBe('800px')
    expect(canvas.style.height).toBe('1000px')
  })
})
