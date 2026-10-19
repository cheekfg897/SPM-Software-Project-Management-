import type { PreparationStatus, PreparationUpdate } from '@/config/preparation'
import type { UnavailabilityCategory } from '@/config/unavailabilityCategories'
import { apiRequest } from '@/lib/api'

/** The venue module's booking request endpoints (SCRUM-42, SCRUM-43, SCRUM-93, SCRUM-75, SCRUM-84). */
const BOOKING_PATHS = {
  EVENT_REQUESTS: (reference: string) => `/api/venues/events/${reference}/booking-requests`,
  /** One of the event's requests, which SCRUM-93 calls a venue arrangement. */
  arrangement: (reference: string, arrangementId: number) =>
    `/api/venues/events/${reference}/booking-requests/${arrangementId}`,
  withdraw: (reference: string, arrangementId: number) =>
    `/api/venues/events/${reference}/booking-requests/${arrangementId}/withdraw`,
  cancelAll: (reference: string) => `/api/venues/events/${reference}/booking-requests/cancel-all`,
  /** Venue Staff's queue, across every event. */
  PENDING: '/api/venues/booking-requests',
  decisionFor: (requestId: number) => `/api/venues/booking-requests/${requestId}/decision`,
  /** POST places a tentative hold; PATCH moves its expiry (SCRUM-75). */
  holdFor: (requestId: number) => `/api/venues/booking-requests/${requestId}/hold`,
  /** Every approved booking, for Venue Staff to prepare (ADR-0080). */
  APPROVED: '/api/venues/booking-requests/approved',
  preparationFor: (requestId: number) => `/api/venues/booking-requests/${requestId}/preparation`,
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
  /**
   * A flagged arrangement of the same event this request replaces; approving it releases that
   * one (SCRUM-92). The backend then also accepts an event in Safety Review.
   */
  replaces_request_id?: number
}

/**
 * What the backend accepts when a coordinator changes a pending arrangement (SCRUM-93). Only
 * the fields sent change; the venue and the period never do.
 */
export interface ArrangementChange {
  purpose?: string
  expected_occupancy?: number
  /** `null` clears the layout. */
  required_layout?: string | null
  justification?: string
}

/**
 * Where a request stands. `conflicting` is a pending request that clashes with one Venue Staff
 * approved (SCRUM-44). `on_hold` is a venue Venue Staff hold tentatively until the request's
 * `hold_expires_at` (SCRUM-75). `withdrawn` is the coordinator's retraction (SCRUM-93).
 * `expired` is a hold that ran out before Venue Staff's final approval, so the venue was
 * released (SCRUM-94). `released` is one an approved replacement took over from (SCRUM-92).
 */
export type BookingRequestStatus =
  | 'pending'
  | 'conflicting'
  | 'on_hold'
  | 'approved'
  | 'rejected'
  | 'withdrawn'
  | 'expired'
  | 'released'

/** One reason a booking needs an alternative venue: a block, or the venue's deactivation. */
export interface Unavailability {
  category: UnavailabilityCategory
  /** Venue Staff's note. */
  reason: string
  /** ISO date-times in business time; `ends_at` is `null` until a deactivated venue is reactivated. */
  starts_at: string
  ends_at: string | null
}

/**
 * One reason a significant change to the event flagged a booking (SCRUM-33 AC6): Venue Staff
 * must reconfirm it, or its venue no longer suits it, with what changed or what it now fails.
 */
export interface ReassessmentFlag {
  kind: 'requires_reconfirmation' | 'no_longer_suitable'
  reason: string
}

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
  /** Venue Staff's progress in preparing the venue, and their notes (SCRUM-84). */
  preparation_status: PreparationStatus
  preparation_notes: string | null
  /**
   * When an `on_hold` request's hold expires, or an `expired` one's did, in business time;
   * otherwise null.
   */
  hold_expires_at: string | null
  /** Flagged "Needs Alternative Venue": its venue became unavailable (SCRUM-92). */
  needs_alternative_venue: boolean
  /** Every block or deactivation that flagged it, earliest first; kept once it is released. */
  unavailability: Unavailability[]
  /** The flagged arrangement this one replaces, if it is a replacement (SCRUM-92). */
  replaces_request_id: number | null
  /** Flagged by a significant change to the event, until it is reconfirmed or replaced (SCRUM-33). */
  flagged_after_change: boolean
  /** Each reason a change flagged it, oldest first; kept once it is released. */
  reassessment_flags: ReassessmentFlag[]
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
  approved: () => [...bookingKeys.all, 'approved'] as const,
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

/** Change a pending arrangement; the backend answers with it as it now is. */
export function changeArrangement(
  reference: string,
  arrangementId: number,
  change: ArrangementChange,
): Promise<BookingRequest> {
  return apiRequest<BookingRequest>(BOOKING_PATHS.arrangement(reference, arrangementId), {
    method: 'PATCH',
    body: change,
  })
}

/** Withdraw one arrangement; the event's others are left as they are. */
export function withdrawArrangement(
  reference: string,
  arrangementId: number,
): Promise<BookingRequest> {
  return apiRequest<BookingRequest>(BOOKING_PATHS.withdraw(reference, arrangementId), {
    method: 'POST',
  })
}

/** Withdraw every arrangement the event still has; answers with the ones it withdrew. */
export function cancelAllArrangements(reference: string): Promise<BookingRequest[]> {
  return apiRequest<BookingRequest[]>(BOOKING_PATHS.cancelAll(reference), { method: 'POST' })
}

/** What the backend accepts to place a hold or move its expiry (SCRUM-75 AC3, AC4). */
export interface HoldExpiry {
  /** ISO date-time with an offset, in business time: in the future and before the event starts. */
  expires_at: string
}

/** Hold the request's venue tentatively until the expiry, instead of booking it (SCRUM-75). */
export function placeBookingHold(requestId: number, hold: HoldExpiry): Promise<BookingRequest> {
  return apiRequest<BookingRequest>(BOOKING_PATHS.holdFor(requestId), {
    method: 'POST',
    body: hold,
  })
}

/** Move the expiry of a request's active hold (SCRUM-75 AC4). */
export function changeHoldExpiry(requestId: number, hold: HoldExpiry): Promise<BookingRequest> {
  return apiRequest<BookingRequest>(BOOKING_PATHS.holdFor(requestId), {
    method: 'PATCH',
    body: hold,
  })
}

/** Every approved booking, ordered by the backend: earliest event first (ADR-0080). */
export function fetchApprovedBookingRequests(): Promise<BookingRequest[]> {
  return apiRequest<BookingRequest[]>(BOOKING_PATHS.APPROVED)
}

/** Record an approved booking's preparation status and notes (SCRUM-84). Venue Staff only. */
export function updateBookingPreparation(
  requestId: number,
  update: PreparationUpdate,
): Promise<BookingRequest> {
  return apiRequest<BookingRequest>(BOOKING_PATHS.preparationFor(requestId), {
    method: 'PUT',
    body: update,
  })
}
