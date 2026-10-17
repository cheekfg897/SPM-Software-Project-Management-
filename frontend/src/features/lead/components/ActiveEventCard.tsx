import { useId } from 'react'
import { Link } from 'react-router'

import { StatusChip } from '@/components/ui'
import { ROUTES } from '@/config/routes'

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
 * One active event: what it is, when, its status and who holds it, then the way to move it. An
 * event nobody holds can't be reassigned, so it points to the queue instead (docs/adr/0052). It
 * doesn't open the event: the backend refuses the Lead an event's record.
 */
export function ActiveEventCard({ event }: { event: ActiveEvent }) {
  const headingId = useId()
  return (
    <article aria-labelledby={headingId} className="border-line bg-surface rounded-2xl border p-6">
      <h3 id={headingId} className="font-display text-xl font-semibold">
        {event.name}
      </h3>
      <p className="text-ink-faint mt-1 text-sm">{event.reference}</p>
      <dl className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Detail term="Date">{formatEventDates(event.proposed_date, event.end_date)}</Detail>
        <Detail term="Time">{formatProposedTimes(event.start_time, event.end_time)}</Detail>
        <Detail term="Status">
          <StatusChip status={event.status} />
        </Detail>
        <Detail term="Coordinator">{event.coordinator ?? 'Not assigned'}</Detail>
      </dl>
      {event.coordinator === null ? (
        <Link
          to={ROUTES.LEAD_QUEUE}
          className="text-flare mt-5 inline-block text-sm font-medium hover:underline"
        >
          Assign from the queue
        </Link>
      ) : (
        <ReassignForm event={event} />
      )}
    </article>
  )
}
