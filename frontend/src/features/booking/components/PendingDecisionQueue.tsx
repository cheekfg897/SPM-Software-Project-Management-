import { useId } from 'react'

import type { BookingRequest } from '../api'
import { STATUS_LABELS } from '../constants'
import { usePendingBookingRequests } from '../hooks'

import { BookingDecisionForm } from './BookingDecisionForm'
import { BookingQueryList } from './BookingQueryList'
import { BookingRequestDetails } from './BookingRequestDetails'
import { HoldForm } from './HoldForm'

function WaitingRequest({ request }: { request: BookingRequest }) {
  const headingId = useId()

  return (
    <article
      aria-labelledby={headingId}
      className="border-line bg-surface-raised rounded-xl border p-5 text-sm"
    >
      <h3 id={headingId} className="text-ink text-base font-semibold">
        {request.purpose}
      </h3>
      <div className="mt-1 space-y-1">
        <p className="text-flare font-medium">{STATUS_LABELS[request.status]}</p>
        <BookingRequestDetails request={request} />
        {request.replaces_request_id !== null && (
          <p className="text-ink font-medium">
            Replaces a booking whose venue became unavailable. Approving it releases that booking.
          </p>
        )}
      </div>
      <HoldForm request={request} />
      <BookingDecisionForm requestId={request.id} purpose={request.purpose} />
    </article>
  )
}

/**
 * The booking requests waiting for a decision, in the order the backend sent them, each with
 * its status: Pending and Conflicting ones wait for a first decision or a hold, and On Hold ones
 * for final approval (SCRUM-75).
 */
export function PendingDecisionQueue() {
  const queue = usePendingBookingRequests()

  return (
    <BookingQueryList
      query={queue}
      loadingText="Loading booking requests…"
      emptyText="No booking requests are waiting for a decision."
      itemKey={(request) => request.id}
    >
      {(request) => <WaitingRequest request={request} />}
    </BookingQueryList>
  )
}
