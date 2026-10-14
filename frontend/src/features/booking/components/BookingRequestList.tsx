import { useId } from 'react'

import type { BookingRequest } from '../api'
import { STATUS_LABELS } from '../constants'

import { BookingRequestDetails } from './BookingRequestDetails'

function BookingRequestItem({ request }: { request: BookingRequest }) {
  const headingId = useId()

  return (
    <li
      aria-labelledby={headingId}
      className="border-line bg-surface-raised space-y-1 rounded-xl border p-4 text-sm"
    >
      <div className="flex items-center justify-between gap-3">
        <h3 id={headingId} className="text-ink font-semibold">
          {request.purpose}
        </h3>
        <span className="text-flare font-medium">{STATUS_LABELS[request.status]}</span>
      </div>
      <BookingRequestDetails request={request} />
      {request.decision_reason !== null && (
        <p className="text-ink-muted">Reason: {request.decision_reason}</p>
      )}
    </li>
  )
}

/** The event's venue requests, as the backend returned them. */
export function BookingRequestList({ requests }: { requests: BookingRequest[] }) {
  if (requests.length === 0) {
    return <p className="text-ink-muted">No venue requests yet.</p>
  }
  return (
    <ul className="space-y-3">
      {requests.map((request) => (
        <BookingRequestItem key={request.id} request={request} />
      ))}
    </ul>
  )
}
