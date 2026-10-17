import { useId } from 'react'
import type { ReactNode } from 'react'

interface VenueSectionProps {
  title: string
  /** One line under the heading saying what the section is for. */
  description?: string
  children: ReactNode
}

/** A titled part of a venue page or form; its heading names it for screen readers. */
export function VenueSection({ title, description, children }: VenueSectionProps) {
  const headingId = useId()
  return (
    <section aria-labelledby={headingId} className="mt-12">
      <h2 id={headingId} className="font-display text-ink text-xl font-semibold tracking-tight">
        {title}
      </h2>
      {description !== undefined && <p className="text-ink-muted mt-1 text-sm">{description}</p>}
      <div className="mt-4">{children}</div>
    </section>
  )
}
