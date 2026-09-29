import { useEffect, useState } from 'react'
import type { RefObject } from 'react'

/**
 * How far the page has scrolled through an element taller than the screen: 0 while its top
 * is at the top of the screen, 1 once its bottom reaches the bottom of the screen.
 */
function scrollProgressOf(element: Element): number {
  const { top, height } = element.getBoundingClientRect()
  const scrollableDistance = height - window.innerHeight
  if (scrollableDistance <= 0) {
    return 0
  }
  return Math.min(Math.max(-top / scrollableDistance, 0), 1)
}

/** The scroll progress through the element in `ref`, updated as the page scrolls. */
export function useScrollProgress(ref: RefObject<Element | null>): number {
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    function measure() {
      if (ref.current !== null) {
        setProgress(scrollProgressOf(ref.current))
      }
    }
    measure()
    window.addEventListener('scroll', measure, { passive: true })
    window.addEventListener('resize', measure)
    return () => {
      window.removeEventListener('scroll', measure)
      window.removeEventListener('resize', measure)
    }
  }, [ref])

  return progress
}
