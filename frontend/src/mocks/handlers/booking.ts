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
import { MOCK_BOOKING_EVENTS, MOCK_BOOKING_VENUES } from './bookingFixtures'
import type { MockBookingEvent } from './bookingFixtures'

/**
 * The venue module's booking request endpoints (SCRUM-42), answering as
 * backend/app/modules/venue/routes.py does, error bodies included.
 */

const BOOKING_PATH = '/api/venues/events/:eventId/booking-requests'
const REQUIRED_FIELDS = ['venue_id', 'starts_at', 'ends_at', 'purpose'] as const
/** The backend's EVENT_REQUEST_NOT_FOUND_MESSAGE (events/services.py), also sent for another coordinator's event. */
const EVENT_NOT_FOUND_MESSAGE = 'Event request not found.'
const JUSTIFICATION_REQUIRED_MESSAGE =
  'A justification is required because the venue is not suitable.'
const DUPLICATE_REQUEST_MESSAGE =
  'A pending request for this event, venue and period already exists.'

const events: MockBookingEvent[] = Object.values(MOCK_BOOKING_EVENTS)
const venues = Object.values(MOCK_BOOKING_VENUES)
const requests: BookingRequest[] = []

/** Forget the requests raised since. Runs after every test. */
export function resetMockBooking(): void {
  requests.length = 0
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

function findOwnEvent(eventId: unknown, coordinatorId: number): MockBookingEvent | undefined {
  return events.find(
    (event) => String(event.id) === eventId && event.coordinator_id === coordinatorId,
  )
}

export const bookingHandlers: RequestHandler[] = [
  http.get(BOOKING_PATH, ({ request, params }) => {
    const { user, refusal } = checkCoordinator(request)
    if (refusal !== null || user === undefined) {
      return refusal
    }
    const event = findOwnEvent(params.eventId, user.id)
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

    const event = findOwnEvent(params.eventId, user.id)
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
]
