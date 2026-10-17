import { useId } from 'react'

import { RequestList } from './RequestList'
import type { RequestListProps } from './RequestList'

interface RequestListSectionProps extends Pick<RequestListProps, 'requests' | 'pathFor'> {
  /** The section's heading, which also names its list, e.g. "Your assigned events". */
  title: string
}

/** One role's list on Staff home, under its own heading (SCRUM-24, ADR-0046). */
export function RequestListSection({ title, requests, pathFor }: RequestListSectionProps) {
  const headingId = useId()
  return (
    <section aria-labelledby={headingId} className="mt-12">
      <h2 id={headingId} className="font-display text-2xl font-semibold tracking-tight">
        {title}
      </h2>
      <RequestList requests={requests} label={title} pathFor={pathFor} />
    </section>
  )
}
