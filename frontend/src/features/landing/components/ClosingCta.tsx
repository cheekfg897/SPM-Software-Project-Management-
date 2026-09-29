import { useId } from 'react'

import { ButtonLink } from '@/components/ui'
import { ROUTES } from '@/config/routes'

import { Reveal } from './Reveal'

/** The last band on the page: both ways in, once more, over a warm glow. */
export function ClosingCta() {
  const headingId = useId()

  return (
    <section aria-labelledby={headingId} className="px-4 pt-8 pb-24 sm:px-6">
      <Reveal className="border-line bg-surface relative mx-auto max-w-5xl overflow-hidden rounded-3xl border px-6 py-16 text-center sm:py-20">
        <div
          aria-hidden="true"
          className="absolute inset-x-0 -bottom-1/2 h-full bg-[radial-gradient(ellipse_at_center,var(--color-flare)_0%,var(--color-ember)_25%,var(--color-nebula)_50%,transparent_72%)] opacity-35 blur-2xl"
        />
        <div className="relative">
          <h2
            id={headingId}
            className="font-display text-3xl font-semibold tracking-tight text-balance sm:text-5xl"
          >
            Your next event starts here.
          </h2>
          <p className="text-ink-muted mx-auto mt-4 max-w-md text-pretty">
            Browse what’s on, or create an account to host your own.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <ButtonLink to={ROUTES.EVENTS}>Browse events</ButtonLink>
            <ButtonLink to={ROUTES.SIGN_UP} variant="secondary">
              Create an account
            </ButtonLink>
          </div>
        </div>
      </Reveal>
    </section>
  )
}
