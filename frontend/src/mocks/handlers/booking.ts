import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'

import { ROLE } from '@/config/roles'
import type { BookingRequest } from '@/features/booking/api'
import type { FieldErrors } from '@/lib/api'

import {
  errorResponse,
  notAllowed,
  notAuthenticated,
  readBody,
  validationError,
} from '../responses'

import { accountForRequest } from './auth'
import { MOCK_BOOKING_EVENTS, MOCK_BOOKING_VENUES, MOCK_PENDING_DECISIONS } from './bookingFixtures'
import type { MockBookingEvent } from './bookingFixtures'

/**
 * The venue module's booking request endpoints (SCRUM-42), answering as
 * backend/app/modules/venue/routes.py does, error bodies included.
 */

const BOOKING_PATH = '/api/venues/events/:reference/booking-requests'
const PENDING_PATH = '/api/venues/booking-requests'
const DECISION_PATH = `${PENDING_PATH}/:requestId/decision`
const REQUIRED_FIELDS = ['venue_id', 'starts_at', 'ends_at', 'purpose'] as const
/** The backend's EVENT_REQUEST_NOT_FOUND_MESSAGE (events/services.py), also sent for another coordinator's event. */
const EVENT_NOT_FOUND_MESSAGE = 'Event request not found.'
const JUSTIFICATION_REQUIRED_MESSAGE =
  'A justification is required because the venue is not suitable.'
const DUPLICATE_REQUEST_MESSAGE =
  'A pending request for this event, venue and period already exists.'
/** The backend's messages for deciding a request (venue/services.py, SCRUM-43). */
const BOOKING_REQUEST_NOT_FOUND_MESSAGE = 'Booking request not found.'
export const REJECTION_REASON_REQUIRED_MESSAGE = 'A reason is required to reject a booking request.'
const OUTCOME_ERROR_MESSAGE = 'Outcome must be approved or rejected.'
/** The backend's refusal of a clashing approval (venue/services.py, SCRUM-44), for an overlap. */
function clashMessage(bookingId: number): string {
  return `Cannot approve: booking #${bookingId} already holds this venue during the requested period.`
}

const events: MockBookingEvent[] = Object.values(MOCK_BOOKING_EVENTS)
const venues = Object.values(MOCK_BOOKING_VENUES)
let requests: BookingRequest[] = []

/** Forget the requests raised since, and put the waiting ones back. Runs after every test. */
export function resetMockBooking(): void {
  requests = MOCK_PENDING_DECISIONS.map((waiting) => ({ ...waiting }))
}

resetMockBooking()

/** Whether the caller is Venue Staff, who decide requests; otherwise the response to send. */
function checkVenueStaff(request: Request) {
  const user = accountForRequest(request)
  if (user === undefined) {
    return notAuthenticated()
  }
  if (user.role !== ROLE.VENUE_STAFF) {
    return notAllowed()
  }
  return null
}

/**
 * Whether two requests want the same venue during overlapping periods, whatever their events.
 * The mock leaves out the venue's setup and turnaround, so it only sees periods that overlap
 * themselves.
 */
function overlapsAtSameVenue(first: BookingRequest, second: BookingRequest): boolean {
  return (
    first.venue_id === second.venue_id &&
    Date.parse(first.starts_at) < Date.parse(second.ends_at) &&
    Date.parse(second.starts_at) < Date.parse(first.ends_at)
  )
}

/** The approved request holding the venue during the period, which the backend would find as a confirmed booking. */
function clashingApproval(waiting: BookingRequest): BookingRequest | undefined {
  return requests.find(
    (existing) => existing.status === 'approved' && overlapsAtSameVenue(existing, waiting),
  )
}

/** The backend marks each Pending request that clashes with a newly approved one Conflicting (SCRUM-44). */
function markClashingRequestsConflicting(approved: BookingRequest): void {
  for (const existing of requests) {
    if (
      existing.status === 'pending' &&
      existing.id !== approved.id &&
      overlapsAtSameVenue(existing, approved)
    ) {
      existing.status = 'conflicting'
    }
  }
}

/** The statuses Venue Staff can still decide: the queue lists them and a decision accepts them. */
function isDecidable(existing: BookingRequest): boolean {
  return existing.status === 'pending' || existing.status === 'conflicting'
}

/** The queue's order, as the backend sorts it: event date, then event start, then id. */
function waitingForDecision(): BookingRequest[] {
  return requests
    .filter(isDecidable)
    .sort(
      (left, right) =>
        left.event_proposed_date.localeCompare(right.event_proposed_date) ||
        left.event_start_time.localeCompare(right.event_start_time) ||
        left.id - right.id,
    )
}

function missingFieldErrors(body: Record<string, unknown>): FieldErrors {
  const errors: FieldErrors = {}
  for (const field of REQUIRED_FIELDS) {
    if (body[field] === undefined) {
      errors[field] = ['Missing data for required field.']
    }
  }
  return errors
}

function toRequest(event: MockBookingEvent, body: Record<string, unknown>, id: number) {
  return {
    id,
    event_id: event.id,
    venue_id: body.venue_id,
    starts_at: body.starts_at,
    ends_at: body.ends_at,
    purpose: body.purpose,
    expected_occupancy: body.expected_occupancy ?? event.expected_attendance,
    required_layout: body.required_layout ?? null,
    justification: body.justification ?? null,
    status: 'pending',
    preparation_status: 'not_started',
    preparation_notes: null,
    event_proposed_date: event.proposed_date,
    event_end_date: event.end_date,
    event_start_time: event.start_time,
    event_end_time: event.end_time,
    accessibility_needs: event.accessibility_needs,
  } as BookingRequest // the body was checked above to hold the required fields
}

function isDuplicate(candidate: BookingRequest): boolean {
  return requests.some(
    (existing) =>
      existing.event_id === candidate.event_id &&
      existing.venue_id === candidate.venue_id &&
      existing.starts_at === candidate.starts_at &&
      existing.ends_at === candidate.ends_at,
  )
}

/** Whether the signed-in coordinator may see this event's requests; otherwise the response to send. */
function checkCoordinator(request: Request) {
  const user = accountForRequest(request)
  if (user === undefined) {
    return { user, refusal: notAuthenticated() }
  }
  if (user.role !== ROLE.EVENT_COORDINATOR) {
    return { user, refusal: notAllowed() }
  }
  return { user, refusal: null }
}

function findOwnEvent(reference: unknown, coordinatorId: number): MockBookingEvent | undefined {
  return events.find(
    (event) => event.reference === reference && event.coordinator_id === coordinatorId,
  )
}

export const bookingHandlers: RequestHandler[] = [
  http.get(BOOKING_PATH, ({ request, params }) => {
    const { user, refusal } = checkCoordinator(request)
    if (refusal !== null || user === undefined) {
      return refusal
    }
    const event = findOwnEvent(params.reference, user.id)
    if (event === undefined) {
      return errorResponse(404, 'not_found', EVENT_NOT_FOUND_MESSAGE)
    }
    return HttpResponse.json(requests.filter((existing) => existing.event_id === event.id))
  }),

  http.post(BOOKING_PATH, async ({ request, params }) => {
    const { user, refusal } = checkCoordinator(request)
    if (refusal !== null || user === undefined) {
      return refusal
    }
    const body = await readBody(request)
    const missing = missingFieldErrors(body)
    if (Object.keys(missing).length > 0) {
      return validationError(missing)
    }

    const event = findOwnEvent(params.reference, user.id)
    if (event === undefined) {
      return errorResponse(404, 'not_found', EVENT_NOT_FOUND_MESSAGE)
    }
    if (event.status !== 'approved') {
      return errorResponse(
        409,
        'conflict',
        `Only an approved event can have a venue booking request; this one is ${event.status}.`,
      )
    }

    const created = toRequest(event, body, requests.length + 1)
    const venue = venues.find((candidate) => candidate.id === created.venue_id)
    if (venue === undefined) {
      return validationError({ venue_id: ['Venue not found.'] })
    }
    if (created.expected_occupancy > venue.capacity && created.justification === null) {
      return validationError({ justification: [JUSTIFICATION_REQUIRED_MESSAGE] })
    }
    if (isDuplicate(created)) {
      return errorResponse(409, 'conflict', DUPLICATE_REQUEST_MESSAGE)
    }

    requests.push(created)
    return HttpResponse.json(created, { status: 201 })
  }),

  http.get(PENDING_PATH, ({ request }) => {
    const refusal = checkVenueStaff(request)
    return refusal ?? HttpResponse.json(waitingForDecision())
  }),

  http.post(DECISION_PATH, async ({ request, params }) => {
    const refusal = checkVenueStaff(request)
    if (refusal !== null) {
      return refusal
    }
    const waiting = requests.find((existing) => existing.id === Number(params.requestId))
    if (waiting === undefined) {
      return errorResponse(404, 'not_found', BOOKING_REQUEST_NOT_FOUND_MESSAGE)
    }
    if (!isDecidable(waiting)) {
      return errorResponse(
        409,
        'conflict',
        `Only a pending request can be decided; this one is ${waiting.status}.`,
      )
    }

    const body = await readBody(request)
    if (body.outcome !== 'approved' && body.outcome !== 'rejected') {
      return validationError({ outcome: [OUTCOME_ERROR_MESSAGE] })
    }
    const reason = typeof body.reason === 'string' ? body.reason : null
    if (body.outcome === 'rejected' && reason === null) {
      return validationError({ reason: [REJECTION_REASON_REQUIRED_MESSAGE] })
    }

    if (body.outcome === 'approved') {
      const clash = clashingApproval(waiting)
      if (clash !== undefined) {
        return errorResponse(409, 'conflict', clashMessage(clash.id))
      }
    }

    waiting.status = body.outcome
    waiting.decision_reason = reason
    if (body.outcome === 'approved') {
      markClashingRequestsConflicting(waiting)
    }
    return HttpResponse.json(waiting)
  }),
]
