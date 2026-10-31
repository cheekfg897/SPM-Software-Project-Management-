import { useId } from 'react'
import { Link } from 'react-router'

import { StatusChip } from '@/components/ui'
import { staffEventPath } from '@/config/routes'

import type { UnassignedRequest } from '../api'
import { formatProposedDate, formatProposedTimes, formatSubmittedAt } from '../formatRequest'
import { useAssignCoordinator } from '../hooks'

import { CoordinatorEmailForm } from './CoordinatorEmailForm'
import { Detail } from './Detail'

interface QueuedRequestCardProps {
  request: UnassignedRequest
  /** Called once the backend has given the request to a coordinator. */
  onAssigned: () => void
  /** Called with the backend's refusal, so the queue can say why if the request then leaves it. */
  onRefused: (error: Error) => void
}

/**
 * One request waiting in the queue: what it is, when it is for, its status (SCRUM-24 AC8), a link
 * to its read-only record (SCRUM-24 AC10, ADR-0095), and the form to assign it.
 */
export function QueuedRequestCard({ request, onAssigned, onRefused }: QueuedRequestCardProps) {
  const headingId = useId()
  const assign = useAssignCoordinator({ onAssigned, onRefused })
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
      <dl className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <Detail term="Date">{formatProposedDate(request.proposed_date)}</Detail>
        <Detail term="Time">{formatProposedTimes(request.start_time, request.end_time)}</Detail>
        <Detail term="Expected attendance">{request.expected_attendance}</Detail>
        <Detail term="Submitted">{formatSubmittedAt(request.submitted_at)}</Detail>
        <Detail term="Status">
          <StatusChip status={request.status} />
        </Detail>
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
