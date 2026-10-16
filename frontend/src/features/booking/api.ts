import { apiRequest } from '@/lib/api'

/** The venue module's booking request endpoints (SCRUM-42, SCRUM-43). */
const BOOKING_PATHS = {
  EVENT_REQUESTS: (reference: string) => `/api/venues/events/${reference}/booking-requests`,
  /** Venue Staff's queue, across every event. */
  PENDING: '/api/venues/booking-requests',
  decisionFor: (requestId: number) => `/api/venues/booking-requests/${requestId}/decision`,
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

/**
 * Where a request stands. `conflicting` is a pending request that clashes with one Venue Staff
 * approved (SCRUM-44). The backend adds `on_hold` with SCRUM-75.
 */
export type BookingRequestStatus = 'pending' | 'conflicting' | 'approved' | 'rejected'

/** What the backend accepts when Venue Staff decide a request (SCRUM-43). */
export interface BookingDecision {
  outcome: 'approved' | 'rejected'
  /** Required by the backend to reject; left out of the body when not given. */
  reason?: string
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
  status: BookingRequestStatus
  /** Why Venue Staff decided as they did; required to reject (SCRUM-43). */
  decision_reason: string | null
  /** The event's own timing: dates as `2026-11-10`, times as `09:00:00`, in business time. */
  event_proposed_date: string
  event_end_date: string | null
  event_start_time: string
  event_end_time: string
  accessibility_needs: string | null
}

export const bookingKeys = {
  all: ['booking'] as const,
  forEvent: (reference: string) => [...bookingKeys.all, 'event', reference] as const,
  pending: () => [...bookingKeys.all, 'pending'] as const,
}

export function fetchBookingRequests(reference: string): Promise<BookingRequest[]> {
  return apiRequest<BookingRequest[]>(BOOKING_PATHS.EVENT_REQUESTS(reference))
}

export function raiseBookingRequest(
  reference: string,
  payload: RaiseBookingRequest,
): Promise<BookingRequest> {
  return apiRequest<BookingRequest>(BOOKING_PATHS.EVENT_REQUESTS(reference), {
    method: 'POST',
    body: payload,
  })
}

/** Every request waiting for a decision, ordered by the backend: earliest event first. */
export function fetchPendingBookingRequests(): Promise<BookingRequest[]> {
  return apiRequest<BookingRequest[]>(BOOKING_PATHS.PENDING)
}

export function decideBookingRequest(
  requestId: number,
  decision: BookingDecision,
): Promise<BookingRequest> {
  return apiRequest<BookingRequest>(BOOKING_PATHS.decisionFor(requestId), {
    method: 'POST',
    body: decision,
  })
}
