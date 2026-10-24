import { useId } from 'react'
import { Link } from 'react-router'

import { staffEventPath } from '@/config/routes'

import type { UnassignedRequest } from '../api'
import { formatProposedDate, formatProposedTimes, formatSubmittedAt } from '../formatRequest'
import { useAssignCoordinator } from '../hooks'

import { CoordinatorEmailForm } from './CoordinatorEmailForm'
import { Detail } from './Detail'

interface QueuedRequestCardProps {
  request: UnassignedRequest
}

/**
 * One request waiting in the queue: what it is, when it is for, a link to its read-only record
 * (SCRUM-24 AC10, ADR-0095), and the form to assign it.
 */
export function QueuedRequestCard({ request }: QueuedRequestCardProps) {
  const headingId = useId()
  const assign = useAssignCoordinator()
  return (
    <article aria-labelledby={headingId} className="border-line bg-surface rounded-2xl border p-6">
      <h2 id={headingId} className="font-display text-xl font-semibold">
        {request.name}
      </h2>
      <p className="text-ink-faint mt-1 text-sm">{request.reference}</p>
      <Link
        to={staffEventPath(request.reference)}
        className="text-flare mt-2 inline-block text-sm font-medium hover:underline"
      >
        Open the event record
      </Link>
      <dl className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Detail term="Date">{formatProposedDate(request.proposed_date)}</Detail>
        <Detail term="Time">{formatProposedTimes(request.start_time, request.end_time)}</Detail>
        <Detail term="Expected attendance">{request.expected_attendance}</Detail>
        <Detail term="Submitted">{formatSubmittedAt(request.submitted_at)}</Detail>
      </dl>
      <CoordinatorEmailForm
        reference={request.reference}
        name={request.name}
        verb="Assign"
        mutation={assign}
      />
    </article>
  )
}
