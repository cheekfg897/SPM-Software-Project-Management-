import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'

import { usePrefersReducedMotion } from '../hooks/usePrefersReducedMotion'

/** How much of the element must be on screen before it fades in. */
const REVEAL_THRESHOLD = 0.2

interface RevealProps {
  children: ReactNode
  className?: string
}

/**
 * Fades and lifts its children in the first time they scroll into view. Shows them at once
 * with reduced motion, or in a browser without IntersectionObserver.
 */
export function Reveal({ children, className = '' }: RevealProps) {
  // A callback ref (state, not useRef), so the effect runs again once the element exists.
  const [element, setElement] = useState<HTMLDivElement | null>(null)
  const [hasEntered, setHasEntered] = useState(false)
  const prefersReducedMotion = usePrefersReducedMotion()
  const canWatchScrolling = typeof window.IntersectionObserver === 'function'
  const isRevealed = hasEntered || prefersReducedMotion || !canWatchScrolling

  useEffect(() => {
    if (isRevealed || element === null) {
      return
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setHasEntered(true)
          observer.disconnect()
        }
      },
      { threshold: REVEAL_THRESHOLD },
    )
    observer.observe(element)
    return () => observer.disconnect()
  }, [element, isRevealed])

  const motionClasses = isRevealed ? 'translate-y-0 opacity-100' : 'translate-y-8 opacity-0'
  return (
    <div
      ref={setElement}
      data-revealed={isRevealed}
      className={`transition duration-700 ease-out ${motionClasses} ${className}`}
    >
      {children}
    </div>
  )
}
