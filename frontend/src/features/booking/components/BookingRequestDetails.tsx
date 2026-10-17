import { LAYOUT_OPTIONS } from '@/config/roomLayouts'
import { formatShortDate, formatTimeRange } from '@/lib/formatDate'

import type { BookingRequest } from '../api'

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

/**
 * What a booking request asks for and when its event runs, as the backend sent it
 * (SCRUM-42 AC4): the coordinator's list and Venue Staff's queue both show this.
 */
export function BookingRequestDetails({ request }: { request: BookingRequest }) {
  return (
    <>
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
    </>
  )
}
