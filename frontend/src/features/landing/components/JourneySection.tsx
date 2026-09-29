import { useId } from 'react'

import { Reveal } from './Reveal'
import { SectionHeading } from './SectionHeading'

/** How an event comes together, following the event status model (SCRUM-22). */
const JOURNEY_STEPS = [
  { title: 'Request', body: 'An organiser describes the event they have in mind.' },
  { title: 'Review', body: 'A coordinator checks it and lines up the venue and the equipment.' },
  { title: 'Confirmed', body: 'Everything’s in place and the event is locked in.' },
  { title: 'Registrations open', body: 'Attendees find it here and save their place.' },
]

export function JourneySection() {
  const headingId = useId()

  return (
    <section aria-labelledby={headingId} className="mx-auto max-w-6xl px-4 py-20 sm:px-6 sm:py-28">
      <Reveal>
        <SectionHeading
          id={headingId}
          eyebrow="How it works"
          title="From request to registration."
        />
        <div className="relative mt-12">
          {/* The orbit line the steps sit on, on wide screens where they share one row. */}
          <span
            aria-hidden="true"
            className="from-corona via-flare to-nebula absolute inset-x-0 top-4 hidden h-px bg-gradient-to-r opacity-50 lg:block"
          />
          <ol className="relative grid gap-8 sm:grid-cols-2 lg:grid-cols-4 lg:gap-6">
            {JOURNEY_STEPS.map((step, index) => (
              <li key={step.title} className="relative">
                <span
                  aria-hidden="true"
                  className="bg-void font-display text-corona ring-flare/60 relative flex size-8 items-center justify-center rounded-full text-sm ring-1"
                >
                  {index + 1}
                </span>
                <h3 className="font-display mt-5 text-xl font-semibold">{step.title}</h3>
                <p className="text-ink-muted mt-2 text-pretty">{step.body}</p>
              </li>
            ))}
          </ol>
        </div>
      </Reveal>
    </section>
  )
}
