import { useId } from 'react'
import { Link } from 'react-router'

import { StatusChip } from '@/components/ui'
import { staffEventPath } from '@/config/routes'

import type { CoordinatorWorkload } from '../api'
import { formatEventDates, formatProposedTimes } from '../formatRequest'

/**
 * One coordinator and the active events they hold, in the backend's order, each opening its
 * read-only record (SCRUM-24 AC10, ADR-0095).
 */
export function WorkloadCard({ workload }: { workload: CoordinatorWorkload }) {
  const headingId = useId()
  const { coordinator, event_requests: events } = workload

  return (
    <article
      aria-labelledby={headingId}
      className="border-line/70 bg-surface/70 rounded-2xl border p-5"
    >
      <h3 id={headingId} className="font-display text-lg font-semibold">
        {coordinator}
      </h3>
      {events.length === 0 ? (
        <p className="text-ink-faint mt-3 text-sm">No active events.</p>
      ) : (
        <ul className="mt-3 space-y-3">
          {events.map((event) => (
            <li key={event.reference} className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <Link
                  to={staffEventPath(event.reference)}
                  className="text-ink hover:text-flare block truncate text-sm font-medium hover:underline"
                >
                  {event.name}
                </Link>
                <p className="text-ink-muted text-xs">
                  {formatEventDates(event.proposed_date, event.end_date)} ·{' '}
                  {formatProposedTimes(event.start_time, event.end_time)}
                </p>
              </div>
              <StatusChip status={event.status} />
            </li>
          ))}
        </ul>
      )}
    </article>
  )
}
