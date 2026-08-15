/**
 * Bounding-box coordinate conversion utilities for PDF Review UI (Feature 5 Step 2).
 *
 * Maps W3C Web Annotation-style normalized coordinates (0–1000) to actual canvas pixel dimensions.
 * Governed by CONSTITUTION §3.7 (lib/pdf/ boundary).
 */

import type { BoundingBox } from '../../types/review'

export interface PixelBoundingBox {
  left: number
  top: number
  width: number
  height: number
}

/**
 * Normalizes a 0–1000 bounding box to canvas pixel coordinates.
 *
 * Formula per spec AC-3:
 *   left = (bbox.x0 / 1000) * pageWidth
 *   top = (bbox.y0 / 1000) * pageHeight
 *   width = ((bbox.x1 - bbox.x0) / 1000) * pageWidth
 *   height = ((bbox.y1 - bbox.y0) / 1000) * pageHeight
 *
 * Clamps coordinates to valid [0, pageWidth] / [0, pageHeight] ranges to prevent rendering overflow.
 */
export function normalizeBboxToPixels(
  bbox: BoundingBox,
  pageWidth: number,
  pageHeight: number,
): PixelBoundingBox {
  if (pageWidth <= 0 || pageHeight <= 0) {
    return { left: 0, top: 0, width: 0, height: 0 }
  }

  const clamp = (val: number, min: number, max: number) => Math.max(min, Math.min(val, max))

  const x0 = clamp(bbox.x0, 0, 1000)
  const y0 = clamp(bbox.y0, 0, 1000)
  const x1 = clamp(bbox.x1, 0, 1000)
  const y1 = clamp(bbox.y1, 0, 1000)

  const minX = Math.min(x0, x1)
  const maxX = Math.max(x0, x1)
  const minY = Math.min(y0, y1)
  const maxY = Math.max(y0, y1)

  const left = Math.round((minX / 1000) * pageWidth)
  const top = Math.round((minY / 1000) * pageHeight)
  const width = Math.max(1, Math.round(((maxX - minX) / 1000) * pageWidth))
  const height = Math.max(1, Math.round(((maxY - minY) / 1000) * pageHeight))

  return {
    left,
    top,
    width,
    height,
  }
}
