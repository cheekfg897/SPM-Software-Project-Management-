import { useId } from 'react'
import type { ReactNode } from 'react'

interface ActionCardProps {
  title: string
  /** One line on what the action does, under the title. */
  description: string
  children: ReactNode
}

/** One action on an event's record: what it is, what it does, then its form or button. */
export function ActionCard({ title, description, children }: ActionCardProps) {
  const headingId = useId()
  return (
    <section
      aria-labelledby={headingId}
      className="border-line/60 bg-surface/50 rounded-2xl border p-5"
    >
      <h3 id={headingId} className="font-display text-lg font-semibold tracking-tight">
        {title}
      </h3>
      <p className="text-ink-muted mt-1 text-sm">{description}</p>
      <div className="mt-4 space-y-3">{children}</div>
    </section>
  )
}
