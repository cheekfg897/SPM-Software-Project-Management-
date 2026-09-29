import { useId, useRef } from 'react'
import type { CSSProperties } from 'react'

import { ButtonLink } from '@/components/ui'
import { ROUTES } from '@/config/routes'

import { usePrefersReducedMotion } from '../hooks/usePrefersReducedMotion'
import { useScrollProgress } from '../hooks/useScrollProgress'

import { BlackHoleCanvas } from './BlackHoleCanvas'

/** The words are gone by this share of the way through the hero, leaving the black hole. */
const COPY_FADE_END = 0.3
/** How far the words rise over the whole hero, in pixels. */
const COPY_LIFT_PX = 180

/** The words fade and lift away as the visitor scrolls into the black hole. */
function copyStyle(progress: number): CSSProperties {
  const opacity = Math.max(0, 1 - progress / COPY_FADE_END)
  return {
    opacity,
    transform: `translateY(${-progress * COPY_LIFT_PX}px)`,
    visibility: opacity === 0 ? 'hidden' : 'visible',
  }
}

/**
 * The top of the landing page: a black hole that fills the screen and moves as the visitor
 * scrolls. The section is taller than the screen and the canvas sticks while it scrolls by,
 * so scrolling drives the scene instead of moving it away. With reduced motion it is one
 * screen tall and still.
 */
export function BlackHoleHero() {
  const sectionRef = useRef<HTMLElement>(null)
  const headingId = useId()
  const prefersReducedMotion = usePrefersReducedMotion()
  const scrollProgress = useScrollProgress(sectionRef)
  const progress = prefersReducedMotion ? 0 : scrollProgress

  return (
    <section
      ref={sectionRef}
      aria-labelledby={headingId}
      data-scroll-progress={progress.toFixed(2)}
      className={prefersReducedMotion ? 'relative h-dvh' : 'relative h-[220vh]'}
    >
      <div className="sticky top-0 h-dvh overflow-hidden">
        <BlackHoleCanvas progress={progress} />
        <div
          aria-hidden="true"
          className="to-void pointer-events-none absolute inset-x-0 bottom-0 h-40 bg-gradient-to-b from-transparent"
        />
        <div
          className="relative z-10 mx-auto flex max-w-3xl flex-col items-center px-4 pt-24 text-center sm:px-6 sm:pt-28"
          style={copyStyle(progress)}
        >
          {/* A soft dark pool behind the words, so they read over the glow. */}
          <div
            aria-hidden="true"
            className="absolute inset-x-0 -inset-y-10 -z-10 bg-[radial-gradient(ellipse_at_center,var(--color-void)_20%,transparent_70%)] opacity-80"
          />
          <p className="text-flare text-xs font-semibold tracking-[0.3em] uppercase">
            Organisers and attendees, in one place
          </p>
          <h1
            id={headingId}
            className="font-display mt-4 text-5xl font-semibold tracking-tight text-balance sm:text-7xl"
          >
            Every event finds its orbit.
          </h1>
          <p className="text-ink-muted mt-5 max-w-xl text-base text-pretty sm:text-lg">
            Find what&apos;s on and save your place, or bring your own event and let
            ConnectSphere&apos;s coordinators line up the venue and the kit.
          </p>
          <div className="mt-7 flex flex-wrap justify-center gap-3">
            <ButtonLink to={ROUTES.EVENTS}>Browse events</ButtonLink>
            <ButtonLink to={ROUTES.SIGN_UP} variant="secondary">
              Host an event
            </ButtonLink>
          </div>
        </div>
      </div>
    </section>
  )
}
