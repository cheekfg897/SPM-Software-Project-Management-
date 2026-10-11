import { apiRequest } from '@/lib/api'

/** The venue module's booking request endpoints (SCRUM-42), nested under the event. */
const BOOKING_PATHS = {
  EVENT_REQUESTS: (eventId: number) => `/api/venues/events/${eventId}/booking-requests`,
} as const

/** What the backend accepts when a coordinator raises a request. */
export interface RaiseBookingRequest {
  venue_id: number
  /** ISO date-time with an offset, in business time. */
  starts_at: string
  ends_at: string
  purpose: string
  /** Left out, the backend uses the event's expected attendance. */
  expected_occupancy?: number
  required_layout?: string
  /** Required by the backend when the venue is unsuitable for this request. */
  justification?: string
}

/** A booking request with the details of its event, as Venue Staff and coordinators see it. */
export interface BookingRequest {
  id: number
  event_id: number
  venue_id: number
  starts_at: string
  ends_at: string
  purpose: string
  expected_occupancy: number
  required_layout: string | null
  justification: string | null
  status: 'pending'
  /** The event's own timing: dates as `2026-11-10`, times as `09:00:00`, in business time. */
  event_proposed_date: string
  event_end_date: string | null
  event_start_time: string
  event_end_time: string
  accessibility_needs: string | null
}

export const bookingKeys = {
  all: ['booking'] as const,
  forEvent: (eventId: number) => [...bookingKeys.all, 'event', eventId] as const,
}

export function fetchBookingRequests(eventId: number): Promise<BookingRequest[]> {
  return apiRequest<BookingRequest[]>(BOOKING_PATHS.EVENT_REQUESTS(eventId))
}

export function raiseBookingRequest(
  eventId: number,
  payload: RaiseBookingRequest,
): Promise<BookingRequest> {
  return apiRequest<BookingRequest>(BOOKING_PATHS.EVENT_REQUESTS(eventId), {
    method: 'POST',
    body: payload,
  })
}
