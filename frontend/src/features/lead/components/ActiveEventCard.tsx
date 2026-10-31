import { useId } from 'react'
import { Link } from 'react-router'

import { StatusChip } from '@/components/ui'
import { staffEventPath } from '@/config/routes'

import type { ActiveEvent } from '../api'
import { formatEventDates, formatProposedTimes } from '../formatRequest'
import { useReassignCoordinator } from '../hooks'

import { CoordinatorEmailForm } from './CoordinatorEmailForm'
import { Detail } from './Detail'

/** The form that moves a held event to another coordinator, one mutation per event. */
function ReassignForm({ event }: { event: ActiveEvent }) {
  const reassign = useReassignCoordinator()
  return (
    <CoordinatorEmailForm
      reference={event.reference}
      name={event.name}
      verb="Reassign"
      mutation={reassign}
    />
  )
}

/**
 * One active event: what it is, when, its status and who holds it, then the way to move it. Every
 * active event has a coordinator, so every one can be reassigned (docs/adr/0120). It links to the
 * event's read-only record, which the Lead may open (SCRUM-24 AC10, ADR-0095).
 */
export function ActiveEventCard({ event }: { event: ActiveEvent }) {
  const headingId = useId()
  return (
    <article aria-labelledby={headingId} className="border-line bg-surface rounded-2xl border p-6">
      <h3 id={headingId} className="font-display text-xl font-semibold">
        {event.name}
      </h3>
      <p className="text-ink-faint mt-1 text-sm">{event.reference}</p>
      <Link
        to={staffEventPath(event.reference)}
        className="text-flare mt-2 inline-block text-sm font-medium hover:underline"
      >
        Open the event record
      </Link>
      <dl className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Detail term="Date">{formatEventDates(event.proposed_date, event.end_date)}</Detail>
        <Detail term="Time">{formatProposedTimes(event.start_time, event.end_time)}</Detail>
        <Detail term="Status">
          <StatusChip status={event.status} />
        </Detail>
        <Detail term="Coordinator">{event.coordinator}</Detail>
      </dl>
      <ReassignForm event={event} />
    </article>
  )
}
