import { useId } from 'react'

import { ButtonLink } from '@/components/ui'
import { venuePath } from '@/config/routes'
import { formatShortDate, formatTimeRange } from '@/lib/formatDate'

import type { UpdatedVenue } from '../api'

/** When two things now share the venue, e.g. "10 Nov, 12:30 pm – 12:45 pm". */
function sharedWindow(start: string, end: string): string {
  return `${formatShortDate(start)}, ${formatTimeRange(start, end)}`
}

/**
 * What a new setup or turnaround time made overlap, as the backend reported it once the change
 * was saved (SCRUM-67 AC4, ADR-0033). Nothing was changed or cancelled; Venue Staff decide what
 * to do about each.
 */
export function OverlapReport({ saved }: { saved: UpdatedVenue }) {
  const headingId = useId()
  return (
    <section
      aria-labelledby={headingId}
      className="border-ember/50 bg-ember/10 mt-10 max-w-2xl rounded-2xl border p-6"
    >
      <h2 id={headingId} className="font-display text-ink text-xl font-semibold tracking-tight">
        Saved, but some bookings now overlap
      </h2>
      <p className="text-ink-muted mt-2 text-sm">
        With {saved.name}&apos;s new setup and turnaround times, these confirmed bookings hold the
        venue at the same time as something else. They are still booked: nothing has been changed or
        cancelled.
      </p>
      <ul className="text-ink mt-4 space-y-2 text-sm">
        {saved.overlap_warnings.map((warning) => (
          <li key={warning.booking_ids.join('-')}>
            Bookings {warning.booking_ids.join(' and ')} overlap on{' '}
            {sharedWindow(warning.overlap_start, warning.overlap_end)}
          </li>
        ))}
        {saved.block_overlap_warnings.map((warning) => (
          <li key={`${warning.booking_id}-${warning.block_id}`}>
            Booking {warning.booking_id} runs into block {warning.block_id} on{' '}
            {sharedWindow(warning.overlap_start, warning.overlap_end)}
          </li>
        ))}
      </ul>
      <div className="mt-6">
        <ButtonLink to={venuePath(saved.id)} variant="secondary">
          Back to the venue
        </ButtonLink>
      </div>
    </section>
  )
}
