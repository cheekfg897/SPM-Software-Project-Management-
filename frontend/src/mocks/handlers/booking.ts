import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'

import { ROLE } from '@/config/roles'
import type {
  BookingRequest,
  BookingRequestStatus,
  FlaggedBooking,
  ReassessmentFlag,
  Unavailability,
} from '@/features/booking/api'
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
  MOCK_FLAGGED_DRIFTS,
  MOCK_PENDING_DECISIONS,
  MOCK_SAFETY_APPROVED_EVENT_IDS,
} from './bookingFixtures'
import type { MockBookingEvent } from './bookingFixtures'
import { noticeTime } from './businessTime'
import { MOCK_NOW } from './catalogueFixtures'
import {
  capacityReasonMessage,
  driftAfter,
  NOT_FLAGGED_AFTER_CHANGE_MESSAGE,
  outsideEventErrors,
  periodKeptErrors,
  reasonOf,
  reconfirmationOf,
  reconfirmErrors,
  rejectErrors,
  SETTLED_BY_REPLACEMENT_MESSAGE,
} from './flaggedBookingRules'
import type { Drift } from './flaggedBookingRules'
import {
  PREPARATION_NEEDS_SAFETY_APPROVAL_MESSAGE,
  preparationErrors,
  savedNotes,
} from './preparationRules'
import { FLAGGABLE_STATUSES, reassessmentFlagsFor } from './reassessmentRules'
import type { SignificantChange } from './reassessmentRules'
import {
  NO_SUGGESTION,
  suggestedVenueName,
  suggestionIn,
  suggestionRuleErrors,
  suggestionShapeErrors,
} from './suggestionRules'
import { instantOf } from './venueBlockRules'
import { unknownFieldErrors } from './venueRules'
import { currentMockVenues } from './venues'

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
/** The bookings a change flagged, and reconfirming or rejecting one (SCRUM-59). */
const FLAGGED_PATH = `${PENDING_PATH}/flagged`
const RECONFIRM_PATH = `${PENDING_PATH}/:requestId/reconfirm`
const REJECT_PATH = `${PENDING_PATH}/:requestId/reject`
const REQUIRED_FIELDS = ['venue_id', 'starts_at', 'ends_at', 'purpose'] as const
/** Every field RaiseBookingRequestSchema declares; anything else is an "Unknown field." */
const RAISE_FIELDS = [
  ...REQUIRED_FIELDS,
  'expected_occupancy',
  'required_layout',
  'justification',
  'replaces_request_id',
]
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
/** The backend's NOT_FLAGGED_MESSAGE, for a replacement of an arrangement with no flag (SCRUM-92). */
const NOT_FLAGGED_MESSAGE = 'This venue arrangement does not need an alternative venue.'
/**
 * The backend's SAME_VENUE_MESSAGE: a replacement for a venue that became unavailable is always
 * another venue (SCRUM-92 AC6, ADR-0100).
 */
const SAME_VENUE_MESSAGE = 'A replacement must be at a different venue from the one it replaces.'
/**
 * The backend's LOCKED_PERIOD_MESSAGE: a replacement for a venue that became unavailable keeps the
 * flagged arrangement's date and times (SCRUM-92 AC6, Product Owner 25 Oct, ADR-0108).
 */
function lockedPeriodMessage(replaced: BookingRequest): string {
  return `A replacement keeps the date and times of the booking it replaces: ${noticeTime(Date.parse(replaced.starts_at))} to ${noticeTime(Date.parse(replaced.ends_at))}.`
}
/**
 * As the backend's REPLACEMENT_BOOKING_STATUSES (events/services.py): a flag leaves an event that
 * was not yet Confirmed in Safety Review, so a replacement may be raised there too (ADR-0053).
 */
const REPLACEMENT_EVENT_STATUSES: readonly MockBookingEvent['status'][] = [
  'approved',
  'safety_review',
]
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
/**
 * As the backend's UNAVAILABILITY_FLAGGABLE_STATUSES: a venue becoming unavailable flags a
 * confirmed booking, a request still waiting for a decision, and one On hold, whose hold is a
 * booking too (SCRUM-92 AC1, ADR-0100). A change to the event flags all but On hold (ADR-0094).
 */
const UNAVAILABILITY_FLAGGABLE_STATUSES: readonly BookingRequestStatus[] = [
  'pending',
  'conflicting',
  'on_hold',
  'approved',
]
/** What ChangeArrangementSchema accepts; the venue and the period are not among them. */
const CHANGEABLE_FIELDS = ['purpose', 'expected_occupancy', 'required_layout', 'justification']
const LAYOUT_ERROR_MESSAGE = `Must be one of: ${LAYOUT_OPTIONS.map((option) => option.value).join(', ')}.`

const events: MockBookingEvent[] = Object.values(MOCK_BOOKING_EVENTS)
const venues = Object.values(MOCK_BOOKING_VENUES)
let requests: BookingRequest[] = []
/** What changed under each arrangement since its period was set, by its id (SCRUM-59). */
let drifts = new Map<number, Drift>()

/**
 * Forget the requests raised since, and put back the waiting ones and the decided
 * arrangements, with what changed under the flagged ones. Runs after every test.
 */
export function resetMockBooking(): void {
  const startingRequests: readonly BookingRequest[] = [
    ...MOCK_PENDING_DECISIONS,
    ...Object.values(MOCK_ARRANGEMENTS),
  ]
  requests = startingRequests.map((existing) => ({ ...existing }))
  drifts = new Map(
    Object.entries(MOCK_FLAGGED_DRIFTS).map(([id, drift]) => [Number(id), { ...drift }]),
  )
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

/**
 * Move a request to `status`. Its flags count only while it still holds or asks for its venue, as
 * the backend's needs_alternative_venue and is_flagged_after_change say; once it doesn't, they stay
 * as the record of why (SCRUM-92, SCRUM-33 AC6, ADR-0094, ADR-0100).
 */
function moveTo(request: BookingRequest, status: BookingRequestStatus): void {
  request.status = status
  request.needs_alternative_venue =
    UNAVAILABILITY_FLAGGABLE_STATUSES.includes(status) && request.unavailability.length > 0
  request.flagged_after_change =
    FLAGGABLE_STATUSES.includes(status) && request.reassessment_flags.length > 0
}

/** The backend marks each Pending request that clashes with a newly approved one Conflicting (SCRUM-44). */
function markClashingRequestsConflicting(approved: BookingRequest): void {
  for (const existing of requests) {
    if (
      existing.status === 'pending' &&
      existing.id !== approved.id &&
      overlapsAtSameVenue(existing, approved)
    ) {
      moveTo(existing, 'conflicting')
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

/** PositiveId's message for `replaces_request_id`, or null when it is a whole number from 1. */
function replacesIdError(value: unknown): string | null {
  if (value === null) {
    return 'Field may not be null.'
  }
  if (typeof value !== 'number' || !Number.isInteger(value)) {
    return 'Not a valid integer.'
  }
  return value < 1 ? 'replaces_request_id must be a positive number.' : null
}

/**
 * RaiseBookingRequestSchema's messages: each field it doesn't declare, each required field left
 * out, and a bad replacement id.
 */
function raiseFieldErrors(body: Record<string, unknown>): FieldErrors {
  const errors = unknownFieldErrors(body, RAISE_FIELDS)
  for (const field of REQUIRED_FIELDS) {
    if (body[field] === undefined) {
      errors[field] = [MISSING_FIELD_MESSAGE]
    }
  }
  if (body.replaces_request_id !== undefined) {
    const message = replacesIdError(body.replaces_request_id)
    if (message !== null) {
      errors.replaces_request_id = [message]
    }
  }
  return errors
}

/**
 * The backend's refusal of an event at a status that can't take this request, or null. An
 * ordinary request needs an approved event; a replacement may also be raised in Safety Review.
 */
function eventStatusRefusal(event: MockBookingEvent, isReplacement: boolean) {
  if (isReplacement && !REPLACEMENT_EVENT_STATUSES.includes(event.status)) {
    return errorResponse(
      409,
      'conflict',
      `Only an approved event or one in Safety Review can replace a venue; this one is ${event.status}.`,
    )
  }
  if (!isReplacement && event.status !== 'approved') {
    return errorResponse(
      409,
      'conflict',
      `Only an approved event can have a venue booking request; this one is ${event.status}.`,
    )
  }
  return null
}

function toRequest(event: MockBookingEvent, body: Record<string, unknown>, id: number) {
  /** A new request has no flag: only a block or a deactivation adds one (SCRUM-92). */
  const unavailability: Unavailability[] = []
  /** Nor has it been flagged by a change to its event yet (SCRUM-33 AC6). */
  const reassessmentFlags: ReassessmentFlag[] = []
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
    ...NO_SUGGESTION,
    preparation_status: 'not_started',
    preparation_notes: null,
    hold_expires_at: null,
    needs_alternative_venue: false,
    unavailability,
    replaces_request_id: body.replaces_request_id ?? null,
    flagged_after_change: false,
    reassessment_flags: reassessmentFlags,
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

/** The booking mock's event behind a reference, for the staff record mock (ADR-0095). */
export function bookingEventByReference(reference: string): MockBookingEvent | undefined {
  return events.find((known) => known.reference === reference)
}

/**
 * Free every venue the event still has arranged, as the backend's release_event_arrangements
 * does when the event is rejected during planning (SCRUM-49 AC10, ADR-0093): one Venue Staff
 * haven't approved is withdrawn, one holding its venue (approved or on hold) is released, and a
 * retired one stays as it is. Like the withdraw route here, it writes no history.
 */
export function releaseEventArrangements(reference: string): void {
  const event = events.find((known) => known.reference === reference)
  if (event === undefined) {
    return
  }
  for (const arrangement of requestsOf(event)) {
    if (WITHDRAWABLE_STATUSES.includes(arrangement.status)) {
      moveTo(arrangement, 'withdrawn')
    } else if (!RETIRED_STATUSES.includes(arrangement.status)) {
      moveTo(arrangement, 'released')
    }
  }
}

/**
 * An arrangement in full as the record shows it (RecordVenueArrangementSchema, ADR-0104):
 * everything on it but its ids and its event's timing, with its venue's name, location,
 * capacity, facilities and accessibility features.
 */
function arrangementInFull(arrangement: BookingRequest) {
  const venue = currentMockVenues().find((known) => known.id === arrangement.venue_id)
  if (venue === undefined) {
    throw new Error(`Arrangement ${String(arrangement.id)} is at a venue the mock lacks`)
  }
  return {
    venue_name: venue.name,
    venue_location: venue.location,
    venue_capacity: venue.capacity,
    venue_facilities: venue.facilities,
    venue_accessibility_features: venue.accessibility_features,
    starts_at: arrangement.starts_at,
    ends_at: arrangement.ends_at,
    purpose: arrangement.purpose,
    expected_occupancy: arrangement.expected_occupancy,
    required_layout: arrangement.required_layout,
    justification: arrangement.justification,
    status: arrangement.status,
    decision_reason: arrangement.decision_reason,
    suggested_venue_name: suggestedVenueName(arrangement),
    suggested_starts_at: arrangement.suggested_starts_at,
    suggested_ends_at: arrangement.suggested_ends_at,
    hold_expires_at: arrangement.hold_expires_at,
    needs_alternative_venue: arrangement.needs_alternative_venue,
    unavailability: arrangement.unavailability,
    flagged_after_change: arrangement.flagged_after_change,
    reassessment_flags: arrangement.reassessment_flags,
    preparation_status: arrangement.preparation_status,
    preparation_notes: arrangement.preparation_notes,
  }
}

/**
 * Every one of the event's arrangements, in any status, earliest period first, as the backend's
 * list_every_arrangement_for_record reads them for the organiser's record (SCRUM-24 AC10,
 * SCRUM-93 AC5, ADR-0104).
 */
export function everyArrangementForRecord(reference: string) {
  const event = events.find((known) => known.reference === reference)
  if (event === undefined) {
    return []
  }
  return requestsOf(event).map(arrangementInFull)
}

/**
 * Reassess each of the event's live arrangements after a significant change, flagging only those
 * it affects (SCRUM-33 AC6, `flag_arrangements_after_change`), each judged by its own occupancy
 * and its venue's capacity. The edit mock calls it, so the arrangements read back carry the flags.
 */
export function flagArrangementsAfterChange(reference: string, change: SignificantChange): void {
  const event = events.find((known) => known.reference === reference)
  if (event === undefined) {
    return
  }
  requests = requests.map((existing) => {
    const isLive = existing.event_id === event.id && FLAGGABLE_STATUSES.includes(existing.status)
    if (!isLive) {
      return existing
    }
    // The backend reads every change since the period was set back from the history (SCRUM-59).
    drifts.set(existing.id, driftAfter(drifts.get(existing.id), change))
    const venueCapacity = venues.find((venue) => venue.id === existing.venue_id)?.capacity ?? 0
    const size = { expectedOccupancy: existing.expected_occupancy, venueCapacity }
    const flags = reassessmentFlagsFor(size, change)
    if (flags.length === 0) {
      return existing
    }
    return {
      ...existing,
      flagged_after_change: true,
      reassessment_flags: [...existing.reassessment_flags, ...flags],
    }
  })
}

/** One of the event's own arrangements; an id on another event is as missing as an unknown one. */
function findArrangement(event: MockBookingEvent, arrangementId: unknown) {
  return requests.find(
    (existing) => existing.id === Number(arrangementId) && existing.event_id === event.id,
  )
}

/**
 * The time fields that move a replacement off the flagged arrangement's period, compared as
 * instants as the backend's `_period_changes` does, so the same time written in UTC is no change.
 */
function periodChanges(replaced: BookingRequest, body: Record<string, unknown>): FieldErrors {
  const message = lockedPeriodMessage(replaced)
  const changes: FieldErrors = {}
  if (instantOf(body.starts_at) !== Date.parse(replaced.starts_at)) {
    changes.starts_at = [message]
  }
  if (instantOf(body.ends_at) !== Date.parse(replaced.ends_at)) {
    changes.ends_at = [message]
  }
  return changes
}

/**
 * The backend's refusal of a replacement that doesn't name one of the event's flagged
 * arrangements, or null (SCRUM-92 AC6): flagged because its venue became unavailable, or by a
 * significant change to the event (SCRUM-33 AC6, `_check_replaceable`). Another event's is as
 * missing as an unknown one. A replacement for an arrangement that needs an alternative venue must
 * be at another venue, and then for the arrangement's own date and times (ADR-0108); one flagged
 * only after a change may stay at its venue for a new period, and approving one that overlaps it
 * clashes (ADR-0100).
 */
function replacementRefusal(event: MockBookingEvent, body: Record<string, unknown>) {
  const replaced = findArrangement(event, body.replaces_request_id)
  if (replaced === undefined) {
    return validationError({ replaces_request_id: [ARRANGEMENT_NOT_FOUND_MESSAGE] })
  }
  if (!replaced.needs_alternative_venue && !replaced.flagged_after_change) {
    return validationError({ replaces_request_id: [NOT_FLAGGED_MESSAGE] })
  }
  if (!replaced.needs_alternative_venue) {
    return null
  }
  if (replaced.venue_id === body.venue_id) {
    return validationError({ venue_id: [SAME_VENUE_MESSAGE] })
  }
  const changes = periodChanges(replaced, body)
  return Object.keys(changes).length > 0 ? validationError(changes) : null
}

/**
 * Approving a replacement releases the arrangement it replaces, and its hold if it was On hold,
 * so it no longer needs an alternative venue (SCRUM-92 AC7, ADR-0100) and its change flags stop
 * counting (SCRUM-33 AC6). One that already stopped holding or asking for its venue, say rejected
 * since the replacement was raised, is left as it is, as the backend leaves it.
 */
function releaseReplaced(approved: BookingRequest): void {
  const replaced = requests.find((existing) => existing.id === approved.replaces_request_id)
  if (replaced === undefined || !UNAVAILABILITY_FLAGGABLE_STATUSES.includes(replaced.status)) {
    return
  }
  moveTo(replaced, 'released')
  // The hold is cancelled with it, and the backend shows an expiry only while On hold or Expired.
  replaced.hold_expires_at = null
}

/**
 * Whether the request replaces an arrangement whose venue became unavailable, so must keep its
 * period (SCRUM-92 AC6, ADR-0108), as the backend's `_keeps_its_period` says (SCRUM-70).
 */
function keepsItsPeriod(waiting: BookingRequest): boolean {
  const replaced = requests.find((existing) => existing.id === waiting.replaces_request_id)
  return replaced?.needs_alternative_venue === true
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

/**
 * The bookings a change flagged that Venue Staff settle (`_bookings_to_reassess`, SCRUM-59 AC1):
 * one needing an alternative venue is settled by a replacement instead. Earliest event first.
 */
function flaggedBookings(): FlaggedBooking[] {
  return requests
    .filter((existing) => existing.flagged_after_change && !existing.needs_alternative_venue)
    .sort(byEventDate)
    .map((booking) => ({
      booking,
      reconfirm_with: reconfirmationOf(booking, drifts.get(booking.id)),
    }))
}

/**
 * The flagged booking Venue Staff named, or the response to send: 404 for none, 409 for one with
 * no open flag from a change or one needing an alternative venue (`_flagged_booking`).
 */
function flaggedOrRefusal(requestId: unknown): BookingRequest | Response {
  const booking = findRequest(requestId)
  if (booking === undefined) {
    return notFound(BOOKING_REQUEST_NOT_FOUND_MESSAGE)
  }
  if (!booking.flagged_after_change) {
    return errorResponse(409, 'conflict', NOT_FLAGGED_AFTER_CHANGE_MESSAGE)
  }
  if (booking.needs_alternative_venue) {
    return errorResponse(409, 'conflict', SETTLED_BY_REPLACEMENT_MESSAGE)
  }
  return booking
}

/** A replacement for the booking still waiting for a decision (AC6), if there is one. */
function waitingReplacementOf(booking: BookingRequest): BookingRequest | undefined {
  return requests.find(
    (existing) => existing.replaces_request_id === booking.id && isDecidable(existing),
  )
}

/**
 * Why the moved booking can't be reconfirmed for `moved`'s period, or null (AC2, AC3, AC4, AC6):
 * the backend's order, from a replacement waiting to the event's other arrangements at the venue.
 * The mock knows no venue hours or blocks, and leaves out setup and turnaround, as it does for an
 * approval.
 */
function reconfirmRefusal(booking: BookingRequest, moved: BookingRequest, reason: string | null) {
  const replacement = waitingReplacementOf(booking)
  if (replacement !== undefined) {
    return errorResponse(
      409,
      'conflict',
      `Cannot reconfirm: replacement request #${String(replacement.id)} for this booking is still waiting for a decision.`,
    )
  }
  const kept = periodKeptErrors(
    reconfirmationOf(booking, drifts.get(booking.id)),
    Date.parse(moved.starts_at),
    Date.parse(moved.ends_at),
  )
  if (Object.keys(kept).length > 0) {
    return validationError(kept)
  }
  const outside = outsideEventErrors(
    booking,
    Date.parse(moved.starts_at),
    Date.parse(moved.ends_at),
  )
  if (Object.keys(outside).length > 0) {
    return validationError(outside)
  }
  const capacity = venues.find((venue) => venue.id === booking.venue_id)?.capacity ?? 0
  if (moved.expected_occupancy > capacity && reason === null) {
    return validationError({ reason: [capacityReasonMessage(capacity, moved.expected_occupancy)] })
  }
  const others = requests.filter((existing) => existing.id !== booking.id)
  const clash = others.find(
    (existing) =>
      (existing.status === 'approved' || existing.status === 'on_hold') &&
      overlapsAtSameVenue(existing, moved),
  )
  if (clash !== undefined) {
    return errorResponse(
      409,
      'conflict',
      `Cannot reconfirm: booking #${String(clash.id)} holds this venue from ${noticeTime(Date.parse(clash.starts_at))} to ${noticeTime(Date.parse(clash.ends_at))}, setup and turnaround included.`,
    )
  }
  const sameEvent = others.find(
    (existing) =>
      existing.event_id === booking.event_id &&
      UNAVAILABILITY_FLAGGABLE_STATUSES.includes(existing.status) &&
      overlapsAtSameVenue(existing, moved),
  )
  if (sameEvent !== undefined) {
    return errorResponse(
      409,
      'conflict',
      `Cannot reconfirm: the new period overlaps venue arrangement #${String(sameEvent.id)} of the same event at this venue.`,
    )
  }
  return null
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
    const invalid = raiseFieldErrors(body)
    if (Object.keys(invalid).length > 0) {
      return validationError(invalid)
    }

    const event = findOwnEvent(params.reference, user.id)
    if (event === undefined) {
      return notFound(EVENT_NOT_FOUND_MESSAGE)
    }
    const isReplacement = body.replaces_request_id !== undefined
    const statusRefusal = eventStatusRefusal(event, isReplacement)
    if (statusRefusal !== null) {
      return statusRefusal
    }
    if (isReplacement) {
      const refusal = replacementRefusal(event, body)
      if (refusal !== null) {
        return refusal
      }
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
    const badShape = suggestionShapeErrors(body)
    if (Object.keys(badShape).length > 0) {
      return validationError(badShape)
    }
    const reason = typeof body.reason === 'string' ? body.reason : null
    if (body.outcome === 'rejected' && reason === null) {
      return validationError({ reason: [REJECTION_REASON_REQUIRED_MESSAGE] })
    }
    const suggestion = suggestionIn(body)
    const refusedSuggestion = suggestionRuleErrors(
      suggestion,
      body.outcome,
      keepsItsPeriod(waiting),
    )
    if (Object.keys(refusedSuggestion).length > 0) {
      return validationError(refusedSuggestion)
    }

    // Final approval turns a hold into the booking, so it has nothing to clash with (SCRUM-75).
    if (body.outcome === 'approved' && waiting.status !== 'on_hold') {
      const clash = clashingApproval(waiting)
      if (clash !== undefined) {
        return errorResponse(409, 'conflict', clashMessage(clash.id))
      }
    }

    moveTo(waiting, body.outcome)
    waiting.decision_reason = reason
    Object.assign(waiting, suggestion)
    // The backend shows an expiry only while a request is On Hold or Expired.
    waiting.hold_expires_at = null
    if (body.outcome === 'approved') {
      markClashingRequestsConflicting(waiting)
      releaseReplaced(waiting)
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

    moveTo(arrangement, 'withdrawn')
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
      moveTo(arrangement, 'withdrawn')
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

    moveTo(waiting, 'on_hold')
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

  http.get(FLAGGED_PATH, ({ request }) => {
    const refusal = checkVenueStaff(request)
    return refusal ?? HttpResponse.json(flaggedBookings())
  }),

  // The backend's order: the booking, then the body, then the period's checks.
  http.post(RECONFIRM_PATH, async ({ request, params }) => {
    const refusal = checkVenueStaff(request)
    if (refusal !== null) {
      return refusal
    }
    const booking = flaggedOrRefusal(params.requestId)
    if (booking instanceof Response) {
      return booking
    }
    const body = await readBody(request)
    const errors = reconfirmErrors(body)
    if (Object.keys(errors).length > 0) {
      return validationError(errors)
    }
    const reason = reasonOf(body)
    const moved: BookingRequest = {
      ...booking,
      // reconfirmErrors has just checked both are date-times.
      starts_at: String(body.starts_at),
      ends_at: String(body.ends_at),
      expected_occupancy: reconfirmationOf(booking, drifts.get(booking.id)).expected_occupancy,
    }
    const refused = reconfirmRefusal(booking, moved, reason)
    if (refused !== null) {
      return refused
    }

    Object.assign(booking, moved, { reassessment_flags: [] })
    if (reason !== null) {
      booking.decision_reason = reason
    }
    // Moved clear of every booking, a Conflicting request no longer clashes (AC11).
    moveTo(booking, booking.status === 'conflicting' ? 'pending' : booking.status)
    if (booking.status === 'approved') {
      markClashingRequestsConflicting(booking)
    }
    drifts.delete(booking.id)
    return HttpResponse.json(booking)
  }),

  http.post(REJECT_PATH, async ({ request, params }) => {
    const refusal = checkVenueStaff(request)
    if (refusal !== null) {
      return refusal
    }
    const booking = flaggedOrRefusal(params.requestId)
    if (booking instanceof Response) {
      return booking
    }
    const body = await readBody(request)
    const errors = rejectErrors(body)
    if (Object.keys(errors).length > 0) {
      return validationError(errors)
    }
    const reason = reasonOf(body)
    if (reason === null) {
      return validationError({ reason: [REJECTION_REASON_REQUIRED_MESSAGE] })
    }

    // Rejecting cancels an approved booking's venue booking: the venue is free again (AC5).
    moveTo(booking, 'rejected')
    booking.decision_reason = reason
    return HttpResponse.json(booking)
  }),
]
