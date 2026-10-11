import { useId } from 'react'

import type { UnassignedRequest } from '../api'
import { formatProposedDate, formatProposedTimes, formatSubmittedAt } from '../formatRequest'

import { AssignCoordinatorForm } from './AssignCoordinatorForm'

interface QueuedRequestCardProps {
  request: UnassignedRequest
}

function Detail({ term, children }: { term: string; children: string | number }) {
  return (
    <div>
      <dt className="text-ink-faint text-xs tracking-wide uppercase">{term}</dt>
      <dd className="text-ink mt-0.5">{children}</dd>
    </div>
  )
}

/** One request waiting in the queue: what it is, when it is for, and the form to assign it. */
export function QueuedRequestCard({ request }: QueuedRequestCardProps) {
  const headingId = useId()
  return (
    <article aria-labelledby={headingId} className="border-line bg-surface rounded-2xl border p-6">
      <h2 id={headingId} className="font-display text-xl font-semibold">
        {request.name}
      </h2>
      <p className="text-ink-faint mt-1 text-sm">{request.reference}</p>
      <dl className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Detail term="Date">{formatProposedDate(request.proposed_date)}</Detail>
        <Detail term="Time">{formatProposedTimes(request.start_time, request.end_time)}</Detail>
        <Detail term="Expected attendance">{request.expected_attendance}</Detail>
        <Detail term="Submitted">{formatSubmittedAt(request.submitted_at)}</Detail>
      </dl>
      <AssignCoordinatorForm reference={request.reference} name={request.name} />
    </article>
  )
}
