import { useId } from 'react'

import { formatShortDate, formatTimeRange } from '@/features/catalogue/formatDate'

import type { BookingRequest } from '../api'
import { LAYOUT_OPTIONS } from '../constants'

const STATUS_LABELS: Record<BookingRequest['status'], string> = { pending: 'Pending' }

function layoutLabel(layout: string | null): string {
  const option = LAYOUT_OPTIONS.find((candidate) => candidate.value === layout)
  return option?.label ?? 'No layout set'
}

function eventDates(request: BookingRequest): string {
  if (request.event_end_date === null) {
    return request.event_proposed_date
  }
  return `${request.event_proposed_date} to ${request.event_end_date}`
}

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
      <p className="text-ink-muted">
        Venue {request.venue_id} · {formatShortDate(request.starts_at)},{' '}
        {formatTimeRange(request.starts_at, request.ends_at)}
      </p>
      <p className="text-ink-muted">
        {request.expected_occupancy} guests · {layoutLabel(request.required_layout)}
      </p>
      <p className="text-ink-muted">
        Event: {eventDates(request)}, {request.event_start_time} – {request.event_end_time}
      </p>
      {request.accessibility_needs !== null && (
        <p className="text-ink-muted">Accessibility: {request.accessibility_needs}</p>
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
