import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'

import { ROLE } from '@/config/roles'
import type { BookingRequest, BookingRequestStatus, Unavailability } from '@/features/booking/api'
import { LAYOUT_OPTIONS } from '@/config/roomLayouts'
import type { FieldErrors } from '@/lib/api'

import {
  errorResponse,
  notAllowed,
  notAuthenticated,
  readBody,
  validationError,
} from '../responses'

import { accountForRequest } from './auth'
import {
  MOCK_ARRANGEMENTS,
  MOCK_BOOKING_EVENTS,
  MOCK_BOOKING_VENUES,
  MOCK_PENDING_DECISIONS,
  MOCK_SAFETY_APPROVED_EVENT_IDS,
} from './bookingFixtures'
import type { MockBookingEvent } from './bookingFixtures'
import { MOCK_NOW } from './catalogueFixtures'
import {
  PREPARATION_NEEDS_SAFETY_APPROVAL_MESSAGE,
  preparationErrors,
  savedNotes,
} from './preparationRules'

/**
 * The venue module's booking request endpoints (SCRUM-42, SCRUM-43, SCRUM-93, SCRUM-75, SCRUM-84),
 * answering as backend/app/modules/venue/routes.py does, error bodies included, and Venue Staff's
 * list of events, which backend/app/modules/events/routes.py answers (SCRUM-24 AC4). A hold's
 * expiry is compared with the mocks' "now", MOCK_NOW.
 */

const BOOKING_PATH = '/api/venues/events/:reference/booking-requests'
const ARRANGEMENT_PATH = `${BOOKING_PATH}/:arrangementId`
const WITHDRAW_PATH = `${ARRANGEMENT_PATH}/withdraw`
const CANCEL_ALL_PATH = `${BOOKING_PATH}/cancel-all`
const PENDING_PATH = '/api/venues/booking-requests'
const DECISION_PATH = `${PENDING_PATH}/:requestId/decision`
const VENUE_STAFF_EVENTS_PATH = '/api/events/requests/with-venue-bookings'
const HOLD_PATH = `${PENDING_PATH}/:requestId/hold`
/** Venue Staff's approved bookings, and recording one's preparation (SCRUM-84, ADR-0080). */
const APPROVED_PATH = `${PENDING_PATH}/approved`
const PREPARATION_PATH = `${PENDING_PATH}/:requestId/preparation`
const REQUIRED_FIELDS = ['venue_id', 'starts_at', 'ends_at', 'purpose'] as const
const MISSING_FIELD_MESSAGE = 'Missing data for required field.'
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
/** The backend's messages for holds (venue/services.py, SCRUM-75). */
export const SINGLE_VENUE_HOLD_MESSAGE =
  'A hold can only be placed on a request of an event with more than one venue.'
export const EXPIRY_NOT_BEFORE_EVENT_MESSAGE = 'The expiry must be before the event starts.'
const EXPIRY_NOT_FUTURE_MESSAGE = 'The expiry must be in the future.'
const NOT_A_DATE_TIME_MESSAGE = 'Not a valid datetime.'
/** The backend's refusal of a clashing approval (venue/services.py, SCRUM-44), for an overlap. */
function clashMessage(bookingId: number): string {
  return `Cannot approve: booking #${bookingId} already holds this venue during the requested period.`
}
/** The backend's messages for an event's arrangements (venue/services.py, SCRUM-93). */
const ARRANGEMENT_NOT_FOUND_MESSAGE = 'Venue arrangement not found.'
/**
 * As the backend's WITHDRAWABLE_REQUEST_STATUSES: a rejected arrangement stays active until
 * withdrawn, a conflicting one (SCRUM-44) may be withdrawn like a pending one, and so may one
 * whose hold expired (SCRUM-94). An approved or held one has a booking behind it.
 */
const WITHDRAWABLE_STATUSES: readonly BookingRequestStatus[] = [
  'pending',
  'conflicting',
  'rejected',
  'expired',
]
/**
 * As the backend's RETIRED_REQUEST_STATUSES: withdrawn, or released when an approved replacement
 * took over (SCRUM-92). Cancel all leaves them out.
 */
const RETIRED_STATUSES: readonly BookingRequestStatus[] = ['withdrawn', 'released']
/** What ChangeArrangementSchema accepts; the venue and the period are not among them. */
const CHANGEABLE_FIELDS = ['purpose', 'expected_occupancy', 'required_layout', 'justification']
const LAYOUT_ERROR_MESSAGE = `Must be one of: ${LAYOUT_OPTIONS.map((option) => option.value).join(', ')}.`

const events: MockBookingEvent[] = Object.values(MOCK_BOOKING_EVENTS)
const venues = Object.values(MOCK_BOOKING_VENUES)
let requests: BookingRequest[] = []

/**
 * Forget the requests raised since, and put back the waiting ones and the decided
 * arrangements. Runs after every test.
 */
export function resetMockBooking(): void {
  const startingRequests: readonly BookingRequest[] = [
    ...MOCK_PENDING_DECISIONS,
    ...Object.values(MOCK_ARRANGEMENTS),
  ]
  requests = startingRequests.map((existing) => ({ ...existing }))
}

resetMockBooking()

function notFound(message: string) {
  return errorResponse(404, 'not_found', message)
}

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

/**
 * The approved request, or one on hold, holding the venue during the period: the backend
 * would find it as a confirmed booking or a live hold (SCRUM-75 AC5).
 */
function clashingApproval(waiting: BookingRequest): BookingRequest | undefined {
  return requests.find(
    (existing) =>
      (existing.status === 'approved' || existing.status === 'on_hold') &&
      overlapsAtSameVenue(existing, waiting),
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

/** The statuses Venue Staff can hold: a request not yet approved (SCRUM-75). */
function isHoldable(existing: BookingRequest): boolean {
  return existing.status === 'pending' || existing.status === 'conflicting'
}

/**
 * The statuses Venue Staff can still decide: the queue lists them and a decision accepts them.
 * A request On Hold waits for their final approval (SCRUM-75 AC7).
 */
function isDecidable(existing: BookingRequest): boolean {
  return isHoldable(existing) || existing.status === 'on_hold'
}

/**
 * How many venues the event has arranged: every request but a withdrawn or released one, so a
 * rejected one still counts (SCRUM-75 AC1).
 */
function activeArrangementCount(eventId: number): number {
  return requests.filter(
    (existing) => existing.event_id === eventId && !RETIRED_STATUSES.includes(existing.status),
  ).length
}

/** The request Venue Staff named in the path, if there is one. */
function findRequest(requestId: unknown): BookingRequest | undefined {
  return requests.find((existing) => existing.id === Number(requestId))
}

/** The body's expiry, or the backend's 400 when it is missing or not a date-time. */
function readExpiry(body: Record<string, unknown>): string | Response {
  const expiresAt = body.expires_at
  if (expiresAt === undefined) {
    return validationError({ expires_at: [MISSING_FIELD_MESSAGE] })
  }
  if (typeof expiresAt !== 'string' || Number.isNaN(Date.parse(expiresAt))) {
    return validationError({ expires_at: [NOT_A_DATE_TIME_MESSAGE] })
  }
  return expiresAt
}

/** The backend's 400 for an expiry that has passed or is not before the event starts, or null. */
function expiryOutOfRange(expiresAt: string, held: BookingRequest): Response | null {
  const eventStartsAt = `${held.event_proposed_date}T${held.event_start_time}+08:00`
  if (Date.parse(expiresAt) <= Date.parse(MOCK_NOW)) {
    return validationError({ expires_at: [EXPIRY_NOT_FUTURE_MESSAGE] })
  }
  if (Date.parse(expiresAt) >= Date.parse(eventStartsAt)) {
    return validationError({ expires_at: [EXPIRY_NOT_BEFORE_EVENT_MESSAGE] })
  }
  return null
}

/** The order Venue Staff's lists come in from the backend: event date, then event start, then id. */
function byEventDate(left: BookingRequest, right: BookingRequest): number {
  return (
    left.event_proposed_date.localeCompare(right.event_proposed_date) ||
    left.event_start_time.localeCompare(right.event_start_time) ||
    left.id - right.id
  )
}

function waitingForDecision(): BookingRequest[] {
  return requests.filter(isDecidable).sort(byEventDate)
}

function approvedBookings(): BookingRequest[] {
  return requests.filter((existing) => existing.status === 'approved').sort(byEventDate)
}

/** Whether the Safety Officer has approved the event (SCRUM-84 AC5). */
function hasSafetyApproval(eventId: number): boolean {
  return MOCK_SAFETY_APPROVED_EVENT_IDS.includes(eventId)
}

/** Whether an arrangement still counts towards its event's venues: not retired (ADR-0039). */
function isActive(arrangement: BookingRequest): boolean {
  return !RETIRED_STATUSES.includes(arrangement.status)
}

/**
 * Venue Staff's list: each event with an active booking request, newest first, as the backend's
 * event list row (ADR-0085). The mock's ids stand in for the backend's creation times. The mock
 * always holds the waiting requests, so its list is never empty and never carries the backend's
 * empty-list message.
 */
function eventsWithVenueBookings() {
  const listed = events.filter((event) =>
    requests.some((existing) => existing.event_id === event.id && isActive(existing)),
  )
  return listed
    .sort((left, right) => right.id - left.id)
    .map(({ reference, name, proposed_date, end_date, start_time, end_time, status }) => ({
      reference,
      name,
      proposed_date,
      end_date,
      start_time,
      end_time,
      status,
    }))
}

function missingFieldErrors(body: Record<string, unknown>): FieldErrors {
  const errors: FieldErrors = {}
  for (const field of REQUIRED_FIELDS) {
    if (body[field] === undefined) {
      errors[field] = [MISSING_FIELD_MESSAGE]
    }
  }
  return errors
}

function toRequest(event: MockBookingEvent, body: Record<string, unknown>, id: number) {
  /** A new request has no flag: only a block or a deactivation adds one (SCRUM-92). */
  const unavailability: Unavailability[] = []
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
    hold_expires_at: null,
    needs_alternative_venue: false,
    unavailability,
    replaces_request_id: body.replaces_request_id ?? null,
    event_proposed_date: event.proposed_date,
    event_end_date: event.end_date,
    event_start_time: event.start_time,
    event_end_time: event.end_time,
    accessibility_needs: event.accessibility_needs,
  } as BookingRequest // the body was checked above to hold the required fields
}

/**
 * The statuses whose request holds its event, venue and period, as the backend's partial unique
 * index (uq_venue_booking_requests_pending) lists them. A Conflicting request is still pending
 * a decision, and one On hold has the venue held for it (SCRUM-75), so both hold the slot too.
 */
const SLOT_HOLDING_STATUSES: readonly BookingRequestStatus[] = ['pending', 'conflicting', 'on_hold']

function isDuplicate(candidate: BookingRequest): boolean {
  return requests.some(
    (existing) =>
      SLOT_HOLDING_STATUSES.includes(existing.status) &&
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

/** The mock's suitability check: the venue must hold the request's own occupancy. */
function needsJustification(candidate: BookingRequest): boolean {
  const venue = venues.find((existing) => existing.id === candidate.venue_id)
  const tooSmall = venue !== undefined && candidate.expected_occupancy > venue.capacity
  return tooSmall && candidate.justification === null
}

/** An event's requests as the backend lists them: earliest period first, then by id. */
function inPeriodOrder(eventRequests: BookingRequest[]): BookingRequest[] {
  return [...eventRequests].sort(
    (left, right) => left.starts_at.localeCompare(right.starts_at) || left.id - right.id,
  )
}

function requestsOf(event: MockBookingEvent): BookingRequest[] {
  return inPeriodOrder(requests.filter((existing) => existing.event_id === event.id))
}

/**
 * Whether the event has a venue booking request that is still one of its arrangements: any
 * status but withdrawn or released, as the backend's count_active_arrangements counts them. It
 * locks the event's decision (SCRUM-31 AC7, ADR-0084).
 */
export function hasActiveArrangement(reference: string): boolean {
  const event = events.find((known) => known.reference === reference)
  if (event === undefined) {
    return false
  }
  return requestsOf(event).some((existing) => !RETIRED_STATUSES.includes(existing.status))
}

/** One of the event's own arrangements; an id on another event is as missing as an unknown one. */
function findArrangement(event: MockBookingEvent, arrangementId: unknown) {
  return requests.find(
    (existing) => existing.id === Number(arrangementId) && existing.event_id === event.id,
  )
}

function withdrawRefusal(arrangement: BookingRequest) {
  return errorResponse(
    409,
    'conflict',
    `Only a pending, conflicting, rejected or expired arrangement can be withdrawn; this one is ${arrangement.status}.`,
  )
}

/** The backend's message for a text field that must not be blank, or null when it is fine. */
function textFieldError(value: unknown): string | null {
  if (value === null) {
    return 'Field may not be null.'
  }
  if (typeof value !== 'string') {
    return 'Not a valid string.'
  }
  return value.trim() === '' ? 'Must not be blank.' : null
}

function occupancyError(value: unknown): string | null {
  if (typeof value !== 'number') {
    return 'Not a valid integer.'
  }
  return value < 1 ? 'expected_occupancy must be a positive number.' : null
}

function layoutError(value: unknown): string | null {
  const known = value === null || LAYOUT_OPTIONS.some((option) => option.value === value)
  return known ? null : LAYOUT_ERROR_MESSAGE
}

/**
 * ChangeArrangementSchema's message for one field sent, or null when it is fine. A numeric
 * string, which marshmallow also accepts as an occupancy, is refused here: the web app only
 * sends numbers.
 */
function changeFieldError(field: string, value: unknown): string | null {
  if (!CHANGEABLE_FIELDS.includes(field)) {
    return 'Unknown field.'
  }
  if (field === 'expected_occupancy') {
    return occupancyError(value)
  }
  if (field === 'required_layout') {
    return layoutError(value)
  }
  return textFieldError(value)
}

function changeFieldErrors(body: Record<string, unknown>): FieldErrors {
  const errors: FieldErrors = {}
  for (const [field, value] of Object.entries(body)) {
    const message = changeFieldError(field, value)
    if (message !== null) {
      errors[field] = [message]
    }
  }
  return errors
}

export const bookingHandlers: RequestHandler[] = [
  http.get(BOOKING_PATH, ({ request, params }) => {
    const { user, refusal } = checkCoordinator(request)
    if (refusal !== null || user === undefined) {
      return refusal
    }
    const event = findOwnEvent(params.reference, user.id)
    if (event === undefined) {
      return notFound(EVENT_NOT_FOUND_MESSAGE)
    }
    return HttpResponse.json(requestsOf(event))
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
      return notFound(EVENT_NOT_FOUND_MESSAGE)
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
    if (needsJustification(created)) {
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

  http.get(VENUE_STAFF_EVENTS_PATH, ({ request }) => {
    const refusal = checkVenueStaff(request)
    return refusal ?? HttpResponse.json({ event_requests: eventsWithVenueBookings() })
  }),

  http.post(DECISION_PATH, async ({ request, params }) => {
    const refusal = checkVenueStaff(request)
    if (refusal !== null) {
      return refusal
    }
    const waiting = findRequest(params.requestId)
    if (waiting === undefined) {
      return notFound(BOOKING_REQUEST_NOT_FOUND_MESSAGE)
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

    // Final approval turns a hold into the booking, so it has nothing to clash with (SCRUM-75).
    if (body.outcome === 'approved' && waiting.status !== 'on_hold') {
      const clash = clashingApproval(waiting)
      if (clash !== undefined) {
        return errorResponse(409, 'conflict', clashMessage(clash.id))
      }
    }

    waiting.status = body.outcome
    waiting.decision_reason = reason
    // The backend shows an expiry only while a request is On Hold or Expired.
    waiting.hold_expires_at = null
    if (body.outcome === 'approved') {
      markClashingRequestsConflicting(waiting)
    }
    return HttpResponse.json(waiting)
  }),

  http.post(WITHDRAW_PATH, ({ request, params }) => {
    const { user, refusal } = checkCoordinator(request)
    if (refusal !== null || user === undefined) {
      return refusal
    }
    const event = findOwnEvent(params.reference, user.id)
    if (event === undefined) {
      return notFound(EVENT_NOT_FOUND_MESSAGE)
    }
    const arrangement = findArrangement(event, params.arrangementId)
    if (arrangement === undefined) {
      return notFound(ARRANGEMENT_NOT_FOUND_MESSAGE)
    }
    if (!WITHDRAWABLE_STATUSES.includes(arrangement.status)) {
      return withdrawRefusal(arrangement)
    }

    arrangement.status = 'withdrawn'
    return HttpResponse.json(arrangement)
  }),

  http.post(CANCEL_ALL_PATH, ({ request, params }) => {
    const { user, refusal } = checkCoordinator(request)
    if (refusal !== null || user === undefined) {
      return refusal
    }
    const event = findOwnEvent(params.reference, user.id)
    if (event === undefined) {
      return notFound(EVENT_NOT_FOUND_MESSAGE)
    }
    const active = requestsOf(event).filter(isActive)
    // The backend commits once, so one it cannot withdraw means none of them is.
    const stuck = active.find((existing) => !WITHDRAWABLE_STATUSES.includes(existing.status))
    if (stuck !== undefined) {
      return withdrawRefusal(stuck)
    }

    for (const arrangement of active) {
      arrangement.status = 'withdrawn'
    }
    return HttpResponse.json(active)
  }),

  http.patch(ARRANGEMENT_PATH, async ({ request, params }) => {
    const { user, refusal } = checkCoordinator(request)
    if (refusal !== null || user === undefined) {
      return refusal
    }
    const body = await readBody(request)
    const invalid = changeFieldErrors(body)
    if (Object.keys(invalid).length > 0) {
      return validationError(invalid)
    }

    const event = findOwnEvent(params.reference, user.id)
    if (event === undefined) {
      return notFound(EVENT_NOT_FOUND_MESSAGE)
    }
    const arrangement = findArrangement(event, params.arrangementId)
    if (arrangement === undefined) {
      return notFound(ARRANGEMENT_NOT_FOUND_MESSAGE)
    }
    if (arrangement.status !== 'pending') {
      return errorResponse(
        409,
        'conflict',
        `Only a pending arrangement can be changed; this one is ${arrangement.status}.`,
      )
    }
    // Checked before anything is written, so a refused change leaves the arrangement as it was.
    const changed = { ...arrangement, ...body }
    if (needsJustification(changed)) {
      return validationError({ justification: [JUSTIFICATION_REQUIRED_MESSAGE] })
    }

    Object.assign(arrangement, body)
    return HttpResponse.json(arrangement)
  }),

  http.post(HOLD_PATH, async ({ request, params }) => {
    const refusal = checkVenueStaff(request)
    if (refusal !== null) {
      return refusal
    }
    const waiting = findRequest(params.requestId)
    if (waiting === undefined) {
      return notFound(BOOKING_REQUEST_NOT_FOUND_MESSAGE)
    }
    if (!isHoldable(waiting)) {
      return errorResponse(
        409,
        'conflict',
        `Only a pending or conflicting request can be held; this one is ${waiting.status}.`,
      )
    }
    const expiresAt = readExpiry(await readBody(request))
    if (expiresAt instanceof Response) {
      return expiresAt
    }
    if (activeArrangementCount(waiting.event_id) < 2) {
      return errorResponse(409, 'conflict', SINGLE_VENUE_HOLD_MESSAGE)
    }
    const outOfRange = expiryOutOfRange(expiresAt, waiting)
    if (outOfRange !== null) {
      return outOfRange
    }
    const clash = clashingApproval(waiting)
    if (clash !== undefined) {
      return errorResponse(409, 'conflict', clashMessage(clash.id))
    }

    waiting.status = 'on_hold'
    waiting.hold_expires_at = expiresAt
    return HttpResponse.json(waiting)
  }),

  http.patch(HOLD_PATH, async ({ request, params }) => {
    const refusal = checkVenueStaff(request)
    if (refusal !== null) {
      return refusal
    }
    const held = findRequest(params.requestId)
    if (held === undefined) {
      return notFound(BOOKING_REQUEST_NOT_FOUND_MESSAGE)
    }
    if (held.status !== 'on_hold') {
      return errorResponse(
        409,
        'conflict',
        `Only a request on hold has an expiry to change; this one is ${held.status}.`,
      )
    }
    const expiresAt = readExpiry(await readBody(request))
    if (expiresAt instanceof Response) {
      return expiresAt
    }
    const outOfRange = expiryOutOfRange(expiresAt, held)
    if (outOfRange !== null) {
      return outOfRange
    }

    held.hold_expires_at = expiresAt
    return HttpResponse.json(held)
  }),

  http.get(APPROVED_PATH, ({ request }) => {
    const refusal = checkVenueStaff(request)
    return refusal ?? HttpResponse.json(approvedBookings())
  }),

  // The backend's order: the body, then the booking, then its status, then the safety approval.
  http.put(PREPARATION_PATH, async ({ request, params }) => {
    const refusal = checkVenueStaff(request)
    if (refusal !== null) {
      return refusal
    }
    const body = await readBody(request)
    const errors = preparationErrors(body)
    if (Object.keys(errors).length > 0) {
      return validationError(errors)
    }
    const booking = findRequest(params.requestId)
    if (booking === undefined) {
      return notFound(BOOKING_REQUEST_NOT_FOUND_MESSAGE)
    }
    if (booking.status !== 'approved') {
      return errorResponse(
        409,
        'conflict',
        `Preparation can only be recorded for an approved booking; this one is ${booking.status}.`,
      )
    }
    if (!hasSafetyApproval(booking.event_id)) {
      return errorResponse(409, 'conflict', PREPARATION_NEEDS_SAFETY_APPROVAL_MESSAGE)
    }

    // preparationErrors has just checked the status is one of the three.
    booking.preparation_status = body.status as BookingRequest['preparation_status']
    booking.preparation_notes = savedNotes(body)
    return HttpResponse.json(booking)
  }),
]
