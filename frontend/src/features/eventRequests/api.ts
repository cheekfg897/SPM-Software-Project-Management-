import { apiRequest } from '@/lib/api'

import type { EventRequestStatus } from '@/config/eventStatus'

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
 * the clarification exchange, oldest first (SCRUM-24 AC9, ADR-0026, ADR-0046). The record's
 * equipment lines aren't read here (ADR-0046).
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
