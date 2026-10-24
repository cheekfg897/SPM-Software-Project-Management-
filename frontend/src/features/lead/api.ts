import type { EventRequestStatus } from '@/config/eventStatus'
import { apiRequest } from '@/lib/api'

/**
 * The Event Coordinator Lead's routes: the queue (SCRUM-95, docs/adr/0036) and the oversight of
 * every active event and each coordinator's workload (SCRUM-96, docs/adr/0041).
 */
const LEAD_PATHS = {
  UNASSIGNED: '/api/events/requests/unassigned',
  ACTIVE: '/api/events/requests/active',
  WORKLOAD: '/api/events/coordinators/workload',
  coordinatorFor: (reference: string) => `/api/events/requests/${reference}/coordinator`,
  reassign: (reference: string) => `/api/events/requests/${reference}/reassign`,
} as const

/**
 * One request waiting in the queue: the reference that names it, the six fields AC2 lists, and its
 * status, which every list shows (SCRUM-24 AC8, ADR-0095).
 */
export interface UnassignedRequest {
  reference: string
  name: string
  proposed_date: string
  start_time: string
  end_time: string
  expected_attendance: number
  /** ISO date-time with an offset, in business time. */
  submitted_at: string
  status: EventRequestStatus
}

export interface UnassignedQueue {
  /** Oldest submission first. */
  event_requests: UnassignedRequest[]
  /** Only present when the queue is empty. */
  message?: string
}

/**
 * An active event as the Lead's lists show it: SCRUM-24 AC8's name, date, time and status. The
 * date is business time with no offset ("2026-11-12"), the times too ("09:00:00").
 */
export interface ListedEvent {
  reference: string
  name: string
  proposed_date: string
  /** Only for an event that ends on a later day. */
  end_date: string | null
  start_time: string
  end_time: string
  status: EventRequestStatus
}

/** A row of the active list: the event and its coordinator's name, never their id. */
export interface ActiveEvent extends ListedEvent {
  /** Null for a submitted event nobody holds yet (docs/adr/0041 decision 5). */
  coordinator: string | null
}

export interface ActiveEvents {
  /** Newest first. */
  event_requests: ActiveEvent[]
  /** Only present when no event is active. */
  message?: string
}

/** One coordinator, by name, and the active events they hold, newest first. */
export interface CoordinatorWorkload {
  coordinator: string
  event_requests: ListedEvent[]
}

export interface Workload {
  /** Ordered by name. */
  coordinators: CoordinatorWorkload[]
  /** Only present when no coordinator holds an active event. */
  message?: string
}

/** The event to hand over, and the Event Coordinator to hand it to, named by email. */
export interface CoordinatorChoice {
  reference: string
  coordinator_email: string
}

/** The request after it was assigned or reassigned. The backend sends its other fields too. */
export interface AssignedRequest {
  reference: string
  name: string
  status: EventRequestStatus
  coordinator: { full_name: string; email: string }
}

/**
 * No key names the viewer: every Lead gets the same answers (SCRUM-96's Assumption), any other
 * role is refused, and logging out clears the cache (docs/adr/0062 decision 7).
 */
export const leadKeys = {
  all: ['lead'] as const,
  queue: () => [...leadKeys.all, 'queue'] as const,
  oversight: () => [...leadKeys.all, 'oversight'] as const,
  active: () => [...leadKeys.oversight(), 'active'] as const,
  workload: () => [...leadKeys.oversight(), 'workload'] as const,
}

export function fetchUnassignedQueue(): Promise<UnassignedQueue> {
  return apiRequest<UnassignedQueue>(LEAD_PATHS.UNASSIGNED)
}

export function fetchActiveEvents(): Promise<ActiveEvents> {
  return apiRequest<ActiveEvents>(LEAD_PATHS.ACTIVE)
}

export function fetchCoordinatorWorkload(): Promise<Workload> {
  return apiRequest<Workload>(LEAD_PATHS.WORKLOAD)
}

/** Give a request in the queue to the Event Coordinator with this email address. */
export function assignCoordinator({
  reference,
  coordinator_email,
}: CoordinatorChoice): Promise<AssignedRequest> {
  return apiRequest<AssignedRequest>(LEAD_PATHS.coordinatorFor(reference), {
    method: 'POST',
    body: { coordinator_email },
  })
}

/** Move an assigned, active event to the Event Coordinator with this email address. */
export function reassignCoordinator({
  reference,
  coordinator_email,
}: CoordinatorChoice): Promise<AssignedRequest> {
  return apiRequest<AssignedRequest>(LEAD_PATHS.reassign(reference), {
    method: 'POST',
    body: { coordinator_email },
  })
}
