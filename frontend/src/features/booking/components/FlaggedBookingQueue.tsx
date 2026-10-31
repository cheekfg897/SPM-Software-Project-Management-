import { useId } from 'react'

import type { FlaggedBooking } from '../api'
import { STATUS_LABELS } from '../constants'
import { useFlaggedBookings } from '../hooks'

import { BookingQueryList } from './BookingQueryList'
import { BookingRequestDetails } from './BookingRequestDetails'
import { ChangeFlagReasons } from './ChangeFlagReasons'
import { ReconfirmForm } from './ReconfirmForm'

function FlaggedEntry({ flagged }: { flagged: FlaggedBooking }) {
  const headingId = useId()
  const { booking, reconfirm_with: reconfirmWith } = flagged

  return (
    <article
      aria-labelledby={headingId}
      className="border-line bg-surface-raised rounded-xl border p-5 text-sm"
    >
      <h3 id={headingId} className="text-ink text-base font-semibold">
        {booking.purpose}
      </h3>
      <div className="mt-1 space-y-1">
        <p className="text-flare font-medium">{STATUS_LABELS[booking.status]}</p>
        <BookingRequestDetails request={booking} />
        <ChangeFlagReasons flags={booking.reassessment_flags} />
        {booking.status !== 'approved' && (
          <p className="text-ink font-medium">
            Still waiting for a decision: reconfirming moves it to the new period, and it is then
            decided in the queue above.
          </p>
        )}
        <p className="text-ink-muted">
          Expected occupancy once reconfirmed: {reconfirmWith.expected_occupancy}
        </p>
      </div>
      <ReconfirmForm flagged={flagged} />
    </article>
  )
}

/**
 * The bookings a change flagged, in the order the backend sent them, each with why it was
 * flagged and the period and occupancy reconfirming it gives it (SCRUM-59 AC1, AC2, AC10). One
 * Venue Staff haven't decided yet only moves when reconfirmed (AC11).
 */
export function FlaggedBookingQueue() {
  const flagged = useFlaggedBookings()

  return (
    <BookingQueryList
      query={flagged}
      loadingText="Loading flagged bookings…"
      emptyText="No bookings are flagged after a change."
      itemKey={(entry) => entry.booking.id}
    >
      {(entry) => <FlaggedEntry flagged={entry} />}
    </BookingQueryList>
  )
}
