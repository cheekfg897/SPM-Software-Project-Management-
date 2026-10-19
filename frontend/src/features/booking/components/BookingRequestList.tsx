import { useId } from 'react'

import type { BookingRequest } from '../api'
import { RETIRED_STATUSES, STATUS_LABELS } from '../constants'

import { AlternativeVenueNotice } from './AlternativeVenueNotice'
import { ArrangementActions } from './ArrangementActions'
import { BookingRequestDetails } from './BookingRequestDetails'
import { CancelAllArrangements } from './CancelAllArrangements'
import { PreparationSummary } from './PreparationSummary'

interface BookingRequestListProps {
  reference: string
  requests: BookingRequest[]
}

/**
 * How a replacement names the arrangement it replaces: its purpose, or its id when the list
 * doesn't hold it (SCRUM-92). Null for a request that replaces none.
 */
function replacedName(requests: BookingRequest[], request: BookingRequest): string | null {
  const replacesId = request.replaces_request_id
  if (replacesId === null) {
    return null
  }
  const replaced = requests.find((each) => each.id === replacesId)
  return replaced?.purpose ?? `arrangement ${replacesId}`
}

interface BookingRequestItemProps {
  reference: string
  request: BookingRequest
  /** The name of the arrangement this one replaces, or null when it replaces none. */
  replaces: string | null
}

function BookingRequestItem({ reference, request, replaces }: BookingRequestItemProps) {
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
      {replaces !== null && <p className="text-ink-muted">Replaces {replaces}</p>}
      {request.decision_reason !== null && (
        <p className="text-ink-muted">Reason: {request.decision_reason}</p>
      )}
      {/* Venue Staff prepare a booking once it is approved (SCRUM-84). */}
      {request.status === 'approved' && <PreparationSummary preparation={request} />}
      {request.needs_alternative_venue && (
        <AlternativeVenueNotice reference={reference} arrangement={request} />
      )}
      {!RETIRED_STATUSES.includes(request.status) && (
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
          <BookingRequestItem
            key={request.id}
            reference={reference}
            request={request}
            replaces={replacedName(requests, request)}
          />
        ))}
      </ul>
      <CancelAllArrangements reference={reference} />
    </>
  )
}
