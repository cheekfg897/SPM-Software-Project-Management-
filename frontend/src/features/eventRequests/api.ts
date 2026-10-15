import { apiRequest } from '@/lib/api'

import type { EventRequestStatus } from '@/config/eventStatus'

const EVENT_REQUEST_PATHS = {
  MINE: '/api/events/requests',
  DRAFTS: '/api/events/requests/drafts',
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

/** A role's event list. `message` is there only when the list is empty (SCRUM-24 AC10). */
export interface EventRequestList {
  event_requests: EventRequest[]
  message?: string
}

export const eventRequestKeys = {
  all: ['eventRequests'] as const,
  /** The signed-in organiser's list: it depends on whose organisation it is. */
  mine: (viewerId: number | null) => [...eventRequestKeys.all, 'mine', viewerId] as const,
  /** One request, as its organisation's organisers see it. */
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

/** One request of the organiser's organisation, for reopening a draft (SCRUM-20 AC3). */
export function fetchEventRequest(reference: string): Promise<EventRequest> {
  return apiRequest<EventRequest>(requestPath(reference))
}
