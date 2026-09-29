/**
 * Test stand-ins for the browser APIs the landing page's motion relies on and jsdom lacks.
 * Used only by the landing page's tests.
 */

/**
 * Stub `window.matchMedia` so the page sees the given reduced-motion setting. Returns a
 * function that changes the setting, as a user flipping it in their system settings would.
 */
export function stubPrefersReducedMotion(matches: boolean): (nextMatches: boolean) => void {
  const listeners: (() => void)[] = []
  const mediaQueryList = {
    matches,
    addEventListener: (_type: 'change', listener: () => void) => listeners.push(listener),
    removeEventListener: vi.fn(),
  }
  vi.stubGlobal('matchMedia', () => mediaQueryList)

  return (nextMatches) => {
    mediaQueryList.matches = nextMatches
    for (const listener of listeners) {
      listener()
    }
  }
}

/** Make every element report this box, as if laid out on a real screen. */
export function stubElementBox(box: { top: number; height: number }): void {
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue(
    DOMRect.fromRect({ x: 0, y: box.top, width: 1000, height: box.height }),
  )
}

/**
 * Stub `IntersectionObserver`. Returns a function that tells every observer whether its
 * element is on screen, as the browser does when it first observes and on each change.
 */
export function stubIntersectionObserver(): (isIntersecting: boolean) => void {
  const callbacks: IntersectionObserverCallback[] = []
  const disconnect = vi.fn()
  class StubObserver {
    constructor(callback: IntersectionObserverCallback) {
      callbacks.push(callback)
    }
    observe = vi.fn()
    disconnect = disconnect
  }
  vi.stubGlobal('IntersectionObserver', StubObserver)

  return (isIntersecting) => {
    // Only isIntersecting is read, and the observer argument isn't read at all.
    const entry = { isIntersecting } as IntersectionObserverEntry
    for (const callback of callbacks) {
      callback([entry], {} as IntersectionObserver)
    }
  }
}
