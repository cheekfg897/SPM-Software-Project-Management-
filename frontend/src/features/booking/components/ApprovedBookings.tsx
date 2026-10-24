import { useId } from 'react'

import { PreparationForm } from '@/components/preparation/PreparationForm'
import { PreparationSummary } from '@/components/preparation/PreparationSummary'

import type { BookingRequest } from '../api'
import { useApprovedBookingRequests, useUpdateBookingPreparation } from '../hooks'

import { BookingQueryList } from './BookingQueryList'
import { BookingRequestDetails } from './BookingRequestDetails'

function ApprovedBooking({ booking }: { booking: BookingRequest }) {
  const headingId = useId()
  const prepare = useUpdateBookingPreparation(booking.id)

  return (
    <article
      aria-labelledby={headingId}
      className="border-line bg-surface-raised rounded-xl border p-5 text-sm"
    >
      <h3 id={headingId} className="text-ink text-base font-semibold">
        {booking.purpose}
      </h3>
      <div className="mt-1 space-y-1">
        <BookingRequestDetails request={booking} />
        <PreparationSummary preparation={booking} />
      </div>
      <div className="mt-4">
        <PreparationForm subject={booking.purpose} current={booking} mutation={prepare} />
      </div>
    </article>
  )
}

/**
 * Every approved booking, each with what its preparation is and a form to record more
 * (SCRUM-84 AC1, ADR-0080). Recording waits for the Safety Officer's approval, which the
 * backend checks.
 */
export function ApprovedBookings() {
  const approved = useApprovedBookingRequests()

  return (
    <BookingQueryList
      query={approved}
      loadingText="Loading approved bookings…"
      emptyText="No approved bookings to prepare."
    >
      {(booking) => <ApprovedBooking booking={booking} />}
    </BookingQueryList>
  )
}
