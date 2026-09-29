import { useEffect, useState } from 'react'

const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)'

/** A browser without matchMedia (jsdom, very old ones) can't say, so motion is allowed. */
function canAskTheBrowser(): boolean {
  return typeof window.matchMedia === 'function'
}

function readPreference(): boolean {
  return canAskTheBrowser() && window.matchMedia(REDUCED_MOTION_QUERY).matches
}

/** True when the user has asked their system for less motion. Follows changes live. */
export function usePrefersReducedMotion(): boolean {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(readPreference)

  useEffect(() => {
    if (!canAskTheBrowser()) {
      return
    }
    const mediaQuery = window.matchMedia(REDUCED_MOTION_QUERY)
    const handleChange = () => setPrefersReducedMotion(mediaQuery.matches)
    mediaQuery.addEventListener('change', handleChange)
    return () => mediaQuery.removeEventListener('change', handleChange)
  }, [])

  return prefersReducedMotion
}
