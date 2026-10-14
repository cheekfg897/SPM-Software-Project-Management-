import { useId } from 'react'

import { Button, ErrorAlert, Spinner } from '@/components/ui'

import type { BookingRequest } from '../api'
import { usePendingBookingRequests } from '../hooks'

import { BookingDecisionForm } from './BookingDecisionForm'
import { BookingRequestDetails } from './BookingRequestDetails'

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
        <BookingRequestDetails request={request} />
      </div>
      <BookingDecisionForm requestId={request.id} purpose={request.purpose} />
    </article>
  )
}

/** The booking requests waiting for a decision, in the order the backend sent them. */
export function PendingDecisionQueue() {
  const queue = usePendingBookingRequests()

  if (queue.isPending) {
    return (
      <p role="status" className="text-ink-muted flex items-center gap-3">
        <Spinner />
        Loading booking requests…
      </p>
    )
  }
  if (queue.isError) {
    return (
      <div className="space-y-4">
        <ErrorAlert error={queue.error} />
        <Button variant="secondary" onClick={() => void queue.refetch()}>
          Try again
        </Button>
      </div>
    )
  }
  if (queue.data.length === 0) {
    return (
      <p className="border-line text-ink-muted rounded-2xl border border-dashed px-6 py-16 text-center">
        No booking requests are waiting for a decision.
      </p>
    )
  }
  return (
    <ul className="space-y-5">
      {queue.data.map((request) => (
        <li key={request.id}>
          <WaitingRequest request={request} />
        </li>
      ))}
    </ul>
  )
}
