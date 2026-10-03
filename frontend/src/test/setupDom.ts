/**
 * Shared jsdom setup for component tests. Import at the top of a test file that declares
 * `// @vitest-environment jsdom`.
 *
 * jsdom has no 2D canvas; the viewer only needs `getContext('2d')` to return an object
 * that `page.render()` receives, so a minimal stub is installed here.
 */
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

if (typeof HTMLCanvasElement !== 'undefined') {
  Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', {
    configurable: true,
    value: function getContext(this: HTMLCanvasElement) {
      return { canvas: this, setTransform: () => {} }
    },
  })
}

if (typeof Element !== 'undefined' && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = function scrollIntoView() {}
}

// Node >= 22 ships an experimental global `localStorage` that shadows jsdom's and is
// undefined without --localstorage-file. Install a small in-memory Storage instead.
function memoryStorage(): Storage {
  const data = new Map<string, string>()
  return {
    get length() {
      return data.size
    },
    clear: () => data.clear(),
    getItem: (k: string) => (data.has(k) ? (data.get(k) as string) : null),
    key: (i: number) => Array.from(data.keys())[i] ?? null,
    removeItem: (k: string) => void data.delete(k),
    setItem: (k: string, v: string) => void data.set(k, String(v)),
  }
}
function storageWorks(name: 'localStorage' | 'sessionStorage'): boolean {
  try {
    return typeof globalThis[name]?.getItem === 'function'
  } catch {
    return false
  }
}
for (const name of ['localStorage', 'sessionStorage'] as const) {
  if (!storageWorks(name)) {
    Object.defineProperty(globalThis, name, { configurable: true, value: memoryStorage() })
  }
}

afterEach(() => {
  cleanup()
  localStorage.clear()
})
