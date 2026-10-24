import { apiRequest } from '@/lib/api'

import type { EventRequestStatus } from '@/config/eventStatus'
import type { Preparation } from '@/config/preparation'
import type { BookingRequestStatus } from '@/features/booking/api'
import type { SafetyChecklist, SafetyReviewEquipment } from '@/features/safety/api'
import type { SafetyOutcome } from '@/features/safety/constants'

const EVENT_REQUEST_PATHS = {
  MINE: '/api/events/requests',
  DRAFTS: '/api/events/requests/drafts',
  ASSIGNED: '/api/events/requests/assigned',
} as const

/** One request's path, with its reference escaped so it can't change the path. */
function requestPath(reference: string): string {
  return `${EVENT_REQUEST_PATHS.MINE}/${encodeURIComponent(reference)}`
}

function draftPath(reference: string): string {
  return `${EVENT_REQUEST_PATHS.DRAFTS}/${encodeURIComponent(reference)}`
}

/**
 * An event request as the backend shows it to its organiser. Dates and times are business
 * time with no offset; a draft may leave any of them null (SCRUM-20, ADR-0024).
 */
export interface EventRequest {
  reference: string
  status: EventRequestStatus
  name: string
  purpose: string | null
  description: string | null
  /** e.g. "2026-10-15" */
  proposed_date: string | null
  end_date: string | null
  /** e.g. "09:00:00" */
  start_time: string | null
  end_time: string | null
  expected_attendance: number | null
  venue_requirements: string | null
  accessibility_needs: string | null
  equipment_requirements: string | null
  registration_required: boolean
  /** ISO date-time with an offset. */
  created_at: string | null
}

/** A role's event list. `message` is there only when the list is empty (SCRUM-24 AC11). */
export interface EventRequestList {
  event_requests: EventRequest[]
  message?: string
}

/** The assigned coordinator as an event's record shows them: name and email, never an id. */
export interface CoordinatorContact {
  full_name: string
  email: string
}

/** The coordinator's current ruling on a request (SCRUM-31 AC9, ADR-0028). */
export interface Decision {
  outcome: 'approved' | 'rejected'
  reason: string | null
  decided_by: string | null
  /** ISO date-time with an offset. */
  decided_at: string
}

/** One clarification question and, once given, its answer (SCRUM-32 AC4, ADR-0029). */
export interface Clarification {
  message: string | null
  requested_by: string | null
  requested_at: string
  response: string | null
  answered_by: string | null
  answered_at: string | null
}

/**
 * An event request's record: the request, the coordinator's note the organiser may see, who
 * the coordinator is (null until one is assigned), the decision (null until one is made) and
 * the clarification exchange, oldest first (SCRUM-24 AC9, ADR-0026, ADR-0056). The record's
 * equipment lines aren't read here (ADR-0056).
 */
export interface EventRecord extends EventRequest {
  programme_notes: string | null
  coordinator: CoordinatorContact | null
  decision: Decision | null
  clarifications: Clarification[]
}

export const eventRequestKeys = {
  all: ['eventRequests'] as const,
  /** The signed-in organiser's list: it depends on whose organisation it is. */
  mine: (viewerId: number | null) => [...eventRequestKeys.all, 'mine', viewerId] as const,
  /** The signed-in coordinator's assigned events. */
  assigned: (viewerId: number | null) => [...eventRequestKeys.all, 'assigned', viewerId] as const,
  /** One request's record: whether it opens, and for whom, depends on who is asking. */
  one: (reference: string, viewerId: number | null) =>
    [...eventRequestKeys.all, 'one', viewerId, reference] as const,
}

/** The organiser's client organisation's event requests and their own drafts, newest first. */
export function fetchMyEventRequests(): Promise<EventRequestList> {
  return apiRequest<EventRequestList>(EVENT_REQUEST_PATHS.MINE)
}

/**
 * What the organiser fills in on a request (SCRUM-19 AC1). Only `name` is always sent. Dates are
 * "2026-11-20" and times "19:00", both business time (ADR-0009). Submitting or saving a new
 * draft leaves an empty field out, so a missing required one gets the backend's "Missing data
 * for required field."; changing a draft sends `null` to empty a field (ADR-0024).
 */
export interface EventRequestDetails {
  name: string
  purpose?: string | null
  description?: string | null
  proposed_date?: string | null
  /** Only for an event that ends on a later day; left out, it ends the day it starts (ADR-0002). */
  end_date?: string | null
  start_time?: string | null
  end_time?: string | null
  expected_attendance?: number | null
  venue_requirements?: string | null
  accessibility_needs?: string | null
  equipment_requirements?: string | null
  registration_required?: boolean
}

/** Submit a new request for the organiser's organisation (SCRUM-19). */
export function submitEventRequest(details: EventRequestDetails): Promise<EventRequest> {
  return apiRequest<EventRequest>(EVENT_REQUEST_PATHS.MINE, { method: 'POST', body: details })
}

/** Save a new draft, which needs only a name (SCRUM-20 AC1). */
export function saveDraftEventRequest(details: EventRequestDetails): Promise<EventRequest> {
  return apiRequest<EventRequest>(EVENT_REQUEST_PATHS.DRAFTS, { method: 'POST', body: details })
}

/** Change the fields sent on one of the organiser's own drafts (SCRUM-20 AC3). */
export function updateDraftEventRequest(
  reference: string,
  changes: Partial<EventRequestDetails>,
): Promise<EventRequest> {
  return apiRequest<EventRequest>(draftPath(reference), { method: 'PATCH', body: changes })
}

/** Submit a draft as it was last saved; there is no body (SCRUM-20). */
export function submitDraftEventRequest(reference: string): Promise<EventRequest> {
  return apiRequest<EventRequest>(`${draftPath(reference)}/submit`, { method: 'POST' })
}

/** The events assigned to the signed-in coordinator, newest first (SCRUM-24 AC2). */
export function fetchAssignedEventRequests(): Promise<EventRequestList> {
  return apiRequest<EventRequestList>(EVENT_REQUEST_PATHS.ASSIGNED)
}

/**
 * One request's record, for its organisation's organisers or its assigned coordinator
 * (SCRUM-24 AC9, AC10); anyone else gets the backend's "not found". The edit-draft page reads
 * the request in it (SCRUM-20 AC3).
 */
export function fetchEventRequest(reference: string): Promise<EventRecord> {
  return apiRequest<EventRecord>(requestPath(reference))
}

/**
 * One entry of an event's history (SCRUM-33, ADR-0025). `kind` is one of EVENT_HISTORY_KIND
 * in eventHistory.ts, or one the backend has added since, so it is read as any string.
 * `details` is shaped by the kind, and names people by name, never by id.
 */
export interface EventHistoryEntry {
  kind: string
  /** ISO date-time with an offset. */
  occurred_at: string
  /** Null for the system, or for someone whose account is gone. */
  actor_name: string | null
  details: Record<string, unknown>
}

export interface EventHistory {
  history: EventHistoryEntry[]
}

/** One person registered for an event (SCRUM-55 AC3). */
export interface Registrant {
  name: string
  email: string
  /** ISO date-time with an offset. */
  registered_at: string
  /** "registered", or "withdrawn" once they withdraw (SCRUM-53): listed, but not counted. */
  status: string
}

/**
 * Who registered, oldest first, and the count against the capacity (SCRUM-55 AC4). The
 * capacity, and so the places left, are null until the coordinator sets one (SCRUM-69).
 */
export interface RegistrantList {
  capacity: number | null
  registered_count: number
  places_left: number | null
  items: Registrant[]
}

/** An event's history: staff see all of it, an organiser what the backend shows them. */
export function eventHistoryKey(reference: string, viewerId: number | null) {
  return [...eventRequestKeys.all, 'history', viewerId, reference] as const
}

/** An event's registrants: whether they may be read depends on who is asking. */
export function registrantsKey(reference: string, viewerId: number | null) {
  return [...eventRequestKeys.all, 'registrants', viewerId, reference] as const
}

/**
 * An event's history, oldest first (SCRUM-33 AC4, AC5). Staff may read it, a coordinator only
 * for an event assigned to them, and an organiser for their organisation's events, without the
 * entries the backend keeps internal.
 */
export function fetchEventHistory(reference: string): Promise<EventHistory> {
  return apiRequest<EventHistory>(`${requestPath(reference)}/history`)
}

/**
 * What the assigned coordinator may change on an event (SCRUM-33 AC1, AC2; ADR-0025): only the
 * fields sent change. Dates are "2026-11-20" and times "19:00", business time; a text field
 * sent empty or as null is emptied.
 */
export interface EventEditChanges {
  description?: string | null
  programme_notes?: string | null
  accessibility_needs?: string | null
  internal_planning_notes?: string | null
  proposed_date?: string | null
  end_date?: string | null
  start_time?: string | null
  end_time?: string | null
  expected_attendance?: number | null
  venue_requirements?: string | null
  equipment_requirements?: string | null
}

/** One field an edit changed, as the history records it (SCRUM-33 AC4, ADR-0025). */
export interface FieldChange {
  field: string
  previous_value: string | number | null
  new_value: string | number | null
  /** A change that raises a reassessment of the event's arrangements (AC2). */
  significant: boolean
}

/** The edited event, with the notes only staff see, and what the edit changed. */
export interface EditedEventRequest extends EventRequest {
  programme_notes: string | null
  internal_planning_notes: string | null
  changes: FieldChange[]
}

/** Change the fields sent on an event assigned to the coordinator (SCRUM-33). */
export function editEventRequest(
  reference: string,
  changes: EventEditChanges,
): Promise<EditedEventRequest> {
  return apiRequest<EditedEventRequest>(requestPath(reference), { method: 'PATCH', body: changes })
}

/** Who registered for an event, for its organisation's organisers or its coordinator (SCRUM-55). */
export function fetchRegistrants(reference: string): Promise<RegistrantList> {
  return apiRequest<RegistrantList>(`${requestPath(reference)}/registrations`)
}

/** Move a submitted request assigned to the coordinator to under review (SCRUM-31 AC3). */
export function startEventRequestReview(reference: string): Promise<EventRequest> {
  return apiRequest<EventRequest>(`${requestPath(reference)}/review`, { method: 'POST' })
}

/**
 * The coordinator's ruling. `reason` is left out of a first approval that has none; the backend
 * says when one is needed (SCRUM-31 AC4, AC6; ADR-0028).
 */
export interface DecisionChoice {
  outcome: Decision['outcome']
  reason?: string
}

/** Approve or reject a request assigned to the coordinator, or change its decision (SCRUM-31). */
export function decideEventRequest(
  reference: string,
  decision: DecisionChoice,
): Promise<EventRequest> {
  return apiRequest<EventRequest>(`${requestPath(reference)}/decide`, {
    method: 'POST',
    body: decision,
  })
}

/** Ask the organiser a question about a request under review (SCRUM-32 AC1, ADR-0029). */
export function requestClarification(reference: string, message: string): Promise<EventRequest> {
  return apiRequest<EventRequest>(`${requestPath(reference)}/request-clarification`, {
    method: 'POST',
    body: { message },
  })
}

/**
 * Answer the open question, which sends the request back to review (SCRUM-32 AC2). Only the
 * response is sent: organisers no longer amend a submitted request (ADR-0060).
 */
export function answerClarification(reference: string, response: string): Promise<EventRequest> {
  return apiRequest<EventRequest>(`${requestPath(reference)}/resubmit`, {
    method: 'POST',
    body: { response },
  })
}

/**
 * Send an approved event to the Safety Officer; there is no body. A refusal's `details` name
 * each venue or equipment gap holding it back (SCRUM-97, ADR-0047).
 */
export function sendToSafetyReview(reference: string): Promise<EventRequest> {
  return apiRequest<EventRequest>(`${requestPath(reference)}/safety-review`, { method: 'POST' })
}

/**
 * Confirm an event in safety review once every approval is in; there is no body. A refusal's
 * `details` name the missing safety approval and each venue or equipment gap (SCRUM-49,
 * ADR-0051).
 */
export function confirmEvent(reference: string): Promise<EventRequest> {
  return apiRequest<EventRequest>(`${requestPath(reference)}/confirm`, { method: 'POST' })
}

/** A planning rejection's body: the reason, left out when none was typed (ADR-0093). */
export interface Rejection {
  reason?: string
}

/**
 * Reject an approved event or one in safety review because an essential arrangement can't be
 * met. The backend requires the reason, releases the event's venues, returns its equipment and
 * tells the organiser (SCRUM-49 AC9, AC10, ADR-0093).
 */
export function rejectEvent(reference: string, rejection: Rejection): Promise<EventRequest> {
  return apiRequest<EventRequest>(`${requestPath(reference)}/reject`, {
    method: 'POST',
    body: rejection,
  })
}

/** Mark a confirmed event completed once it has ended; there is no body (SCRUM-68, ADR-0027). */
export function completeEvent(reference: string): Promise<EventRequest> {
  return apiRequest<EventRequest>(`${requestPath(reference)}/complete`, { method: 'POST' })
}

/**
 * An event's registration settings, as the backend answers a change: what the organiser asked
 * for beside what the coordinator set (SCRUM-69, ADR-0043). The capacity is null until set; the
 * withdrawal cut-off is in business time, or null when withdrawals close as the event starts
 * (AC6, ADR-0086).
 */
export interface RegistrationSettings {
  reference: string
  registration_required: boolean
  registration_enabled: boolean
  registration_capacity: number | null
  withdrawal_cut_off: string | null
}

/**
 * A change to the settings: only what is sent changes. A capacity can't be emptied; a cut-off
 * sent as null is cleared.
 */
export interface RegistrationChanges {
  registration_enabled?: boolean
  registration_capacity?: number
  withdrawal_cut_off?: string | null
}

/** Open or close registration for a confirmed event, and set its capacity (SCRUM-69). */
export function updateRegistrationSettings(
  reference: string,
  changes: RegistrationChanges,
): Promise<RegistrationSettings> {
  return apiRequest<RegistrationSettings>(`${requestPath(reference)}/registration`, {
    method: 'PATCH',
    body: changes,
  })
}

/**
 * A row of a staff list that carries only the backend's `EVENT_LIST_FIELDS`: the event's
 * reference, name, dates, times and status (SCRUM-24 AC8, ADR-0026).
 */
export type EventListRow = Pick<
  EventRequest,
  'reference' | 'name' | 'proposed_date' | 'end_date' | 'start_time' | 'end_time' | 'status'
>

/** A staff list of those rows. `message` is there only when the list is empty (SCRUM-24 AC11). */
export interface EventListRows {
  event_requests: EventListRow[]
  message?: string
}

const WITH_EQUIPMENT_PATH = `${EVENT_REQUEST_PATHS.MINE}/with-equipment`

/**
 * Technical Support's list of the events with an equipment request. The same for every one of
 * them, and nobody else may read it, so the viewer isn't part of the key (ADR-0061).
 */
export const WITH_EQUIPMENT_KEY = [...eventRequestKeys.all, 'withEquipment'] as const

/** Every event with an equipment request, newest first, for Technical Support (SCRUM-24 AC5). */
export function fetchEventRequestsWithEquipment(): Promise<EventListRows> {
  return apiRequest<EventListRows>(WITH_EQUIPMENT_PATH)
}

const WITH_VENUE_BOOKINGS_PATH = `${EVENT_REQUEST_PATHS.MINE}/with-venue-bookings`

/**
 * Venue Staff's list of the events with a venue booking request or a booking. One list for all
 * of them (they aren't assigned to venues), and nobody else may read it, so the viewer isn't
 * part of the key (ADR-0085, ADR-0090).
 */
export const WITH_VENUE_BOOKINGS_KEY = [...eventRequestKeys.all, 'withVenueBookings'] as const

/** Every event with a venue booking request or a booking, newest first (SCRUM-24 AC4). */
export function fetchEventRequestsWithVenueBookings(): Promise<EventListRows> {
  return apiRequest<EventListRows>(WITH_VENUE_BOOKINGS_PATH)
}

/** One of the event's venue arrangements on the read-only staff record (SCRUM-84 AC2). */
export interface StaffVenueArrangement extends Preparation {
  venue_name: string
  /** ISO date-times with an offset. */
  starts_at: string
  ends_at: string
  status: BookingRequestStatus
}

/** One equipment reservation on the read-only staff record (SCRUM-85 AC2). */
export interface StaffReservation extends Preparation {
  equipment_type_name: string
  quantity: number
  /** ISO date-times with an offset. */
  starts_at: string
  ends_at: string
  /** Null once the reserver's account is gone. */
  reserved_by: string | null
}

/** The Safety Officer's outcome on the event's current check (SCRUM-98, ADR-0095). */
export interface SafetyCheckOutcome {
  outcome: SafetyOutcome
  /** The officer's note on each of the seven checklist items (SCRUM-98 AC2). */
  checklist: SafetyChecklist
  reason: string | null
  recorded_by: string | null
  /** ISO date-time with an offset. */
  recorded_at: string
}

/**
 * Any submitted event's read-only record, as Venue Staff, Technical Support, the Safety Officer
 * and the Event Coordinator Lead see it (SCRUM-24 AC9, AC10; ADR-0095): the request and both
 * notes, its coordinator, decision and clarifications, its venue arrangements and equipment with
 * their preparation, and its current safety outcome (null until there is one). No registrants.
 */
export interface StaffEventRecord
  extends EventRequest, Pick<EventRecord, 'coordinator' | 'decision' | 'clarifications'> {
  programme_notes: string | null
  internal_planning_notes: string | null
  venue_arrangements: StaffVenueArrangement[]
  /** The equipment requested, by name, with Technical Support's outcome. */
  equipment_lines: SafetyReviewEquipment[]
  equipment_reservations: StaffReservation[]
  safety_outcome: SafetyCheckOutcome | null
}

/** One event's read-only staff record: whether it opens depends on who is asking. */
export function staffRecordKey(reference: string, viewerId: number | null) {
  return [...eventRequestKeys.all, 'staffRecord', viewerId, reference] as const
}

/**
 * Any submitted event's read-only record, for Venue Staff, Technical Support, the Safety Officer
 * and the Lead (SCRUM-24 AC9, AC10). Everyone else is refused; a draft is "not found".
 */
export function fetchStaffEventRecord(reference: string): Promise<StaffEventRecord> {
  return apiRequest<StaffEventRecord>(`${requestPath(reference)}/staff-record`)
}
