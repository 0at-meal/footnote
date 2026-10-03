/**
 * jsdom has no layout, so every element measures 0x0 and a virtualized list (TanStack Virtual,
 * which reads offsetWidth/offsetHeight) cannot decide which rows are visible. This gives the
 * review item list browser-like sizes: a 600px-tall scroll container and 120px-tall rows.
 * Other elements keep jsdom's behaviour (0).
 */
import { vi } from 'vitest'

function sizeOf(el: HTMLElement): { width: number; height: number } | null {
  if (el.classList.contains('review-sidebar__scroll-container')) return { width: 400, height: 600 }
  if (el.hasAttribute('data-index') && el.parentElement?.getAttribute('role') === 'listbox') return { width: 400, height: 120 }
  return null
}

export function stubReviewListLayout(): void {
  vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockImplementation(function (this: HTMLElement) {
    return sizeOf(this)?.height ?? 0
  })
  vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockImplementation(function (this: HTMLElement) {
    return sizeOf(this)?.width ?? 0
  })
  const original = HTMLElement.prototype.getBoundingClientRect
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
    const size = sizeOf(this)
    if (!size) return original.call(this)
    const { width, height } = size
    return { width, height, top: 0, left: 0, right: width, bottom: height, x: 0, y: 0, toJSON: () => ({}) } as DOMRect
  })
}
