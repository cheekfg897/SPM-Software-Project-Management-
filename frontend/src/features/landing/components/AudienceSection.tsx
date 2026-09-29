import { useId } from 'react'

import { Reveal } from './Reveal'
import { SectionHeading } from './SectionHeading'

export interface AudiencePoint {
  title: string
  body: string
}

interface AudienceSectionProps {
  eyebrow: string
  title: string
  description: string
  points: AudiencePoint[]
}

/** What ConnectSphere does for one kind of visitor: a heading beside a stack of points. */
export function AudienceSection({ eyebrow, title, description, points }: AudienceSectionProps) {
  const headingId = useId()

  return (
    <section aria-labelledby={headingId} className="mx-auto max-w-6xl px-4 py-20 sm:px-6 sm:py-28">
      <Reveal className="grid gap-10 md:grid-cols-[2fr_3fr] md:gap-16">
        <SectionHeading id={headingId} eyebrow={eyebrow} title={title} description={description} />
        <ul className="grid gap-4">
          {points.map((point, index) => (
            <li
              key={point.title}
              className="border-line bg-surface/70 hover:border-flare/50 rounded-2xl border p-6 transition"
            >
              <div className="flex items-start gap-4">
                <span
                  aria-hidden="true"
                  className="border-flare/40 font-display text-flare mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full border text-sm"
                >
                  {index + 1}
                </span>
                <div>
                  <h3 className="font-display text-lg font-semibold">{point.title}</h3>
                  <p className="text-ink-muted mt-1 text-pretty">{point.body}</p>
                </div>
              </div>
            </li>
          ))}
        </ul>
      </Reveal>
    </section>
  )
}
