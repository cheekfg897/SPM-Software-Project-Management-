import { useId } from 'react'
import type { ReactNode } from 'react'

interface OversightSectionProps {
  title: string
  /** One line saying what the section shows. */
  description: string
  children: ReactNode
}

/** A titled part of the oversight page, named by its heading for screen readers. */
export function OversightSection({ title, description, children }: OversightSectionProps) {
  const headingId = useId()
  return (
    <section aria-labelledby={headingId} className="mt-12">
      <h2 id={headingId} className="font-display text-2xl font-semibold tracking-tight">
        {title}
      </h2>
      <p className="text-ink-muted mt-2 mb-6">{description}</p>
      {children}
    </section>
  )
}
