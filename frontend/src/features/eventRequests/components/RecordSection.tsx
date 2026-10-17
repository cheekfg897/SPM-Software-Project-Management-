import { useId } from 'react'
import type { ReactNode } from 'react'

/** One section of an event's record: a heading, which names it for screen readers, and its body. */
export function RecordSection({ title, children }: { title: string; children: ReactNode }) {
  const headingId = useId()
  return (
    <section aria-labelledby={headingId} className="mt-12">
      <h2 id={headingId} className="font-display text-xl font-semibold tracking-tight">
        {title}
      </h2>
      <div className="mt-4">{children}</div>
    </section>
  )
}
