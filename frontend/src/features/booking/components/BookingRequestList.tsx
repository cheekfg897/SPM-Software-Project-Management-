import { useId } from 'react'

import type { BookingRequest } from '../api'
import { STATUS_LABELS } from '../constants'

import { ArrangementActions } from './ArrangementActions'
import { BookingRequestDetails } from './BookingRequestDetails'
import { CancelAllArrangements } from './CancelAllArrangements'

interface BookingRequestListProps {
  reference: string
  requests: BookingRequest[]
}

function BookingRequestItem({
  reference,
  request,
}: {
  reference: string
  request: BookingRequest
}) {
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
      {/* A withdrawn arrangement is retired: it stays on record, with nothing left to do. */}
      {request.status !== 'withdrawn' && (
        <ArrangementActions reference={reference} arrangement={request} />
      )}
    </li>
  )
}

/**
 * The event's venue requests, as the backend returned them, each with what the coordinator can
 * do to it, and a way to cancel them all (SCRUM-42, SCRUM-93).
 */
export function BookingRequestList({ reference, requests }: BookingRequestListProps) {
  if (requests.length === 0) {
    return <p className="text-ink-muted">No venue requests yet.</p>
  }
  return (
    <>
      <ul className="space-y-3">
        {requests.map((request) => (
          <BookingRequestItem key={request.id} reference={reference} request={request} />
        ))}
      </ul>
      <CancelAllArrangements reference={reference} />
    </>
  )
}
