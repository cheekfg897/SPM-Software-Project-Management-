import { useId } from 'react'
import { Link } from 'react-router'

import { StatusChip } from '@/components/ui'
import { staffEventPath } from '@/config/routes'

import type { CoordinatorWorkload } from '../api'
import { formatEventDates, formatProposedTimes } from '../formatRequest'

/**
 * One coordinator, how many active events the backend counted for them (0 when they are free,
 * SCRUM-96 AC3), and those events in the backend's order, each opening its read-only record
 * (SCRUM-24 AC10, ADR-0095).
 */
export function WorkloadCard({ workload }: { workload: CoordinatorWorkload }) {
  const headingId = useId()
  const { coordinator, active_count: count, event_requests: events } = workload

  return (
    <article
      aria-labelledby={headingId}
      className="border-line/70 bg-surface/70 rounded-2xl border p-5"
    >
      <h3 id={headingId} className="font-display text-lg font-semibold">
        {coordinator}
      </h3>
      <p className="text-ink-faint mt-1 text-sm">
        {count === 1 ? '1 active event' : `${count} active events`}
      </p>
      {events.length > 0 && (
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
