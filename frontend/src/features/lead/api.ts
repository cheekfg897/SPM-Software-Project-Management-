import { apiRequest } from '@/lib/api'

/** The Event Coordinator Lead's queue, as docs/adr/0036 (SCRUM-95) describes it. */
const LEAD_PATHS = {
  UNASSIGNED: '/api/events/requests/unassigned',
  coordinatorFor: (reference: string) => `/api/events/requests/${reference}/coordinator`,
} as const

/** One request waiting in the queue: the reference that names it, then the six fields AC2 lists. */
export interface UnassignedRequest {
  reference: string
  name: string
  proposed_date: string
  start_time: string
  end_time: string
  expected_attendance: number
  /** ISO date-time with an offset, in business time. */
  submitted_at: string
}

export interface UnassignedQueue {
  /** Oldest submission first. */
  event_requests: UnassignedRequest[]
  /** Only present when the queue is empty. */
  message?: string
}

export interface AssignCoordinatorInput {
  reference: string
  coordinator_email: string
}

/** The request after it was assigned. The backend sends its other fields too. */
export interface AssignedRequest {
  reference: string
  name: string
  coordinator: { full_name: string; email: string }
}

export const leadKeys = {
  all: ['lead'] as const,
  queue: () => [...leadKeys.all, 'queue'] as const,
}

export function fetchUnassignedQueue(): Promise<UnassignedQueue> {
  return apiRequest<UnassignedQueue>(LEAD_PATHS.UNASSIGNED)
}

/** Give a request in the queue to the Event Coordinator with this email address. */
export function assignCoordinator({
  reference,
  coordinator_email,
}: AssignCoordinatorInput): Promise<AssignedRequest> {
  return apiRequest<AssignedRequest>(LEAD_PATHS.coordinatorFor(reference), {
    method: 'POST',
    body: { coordinator_email },
  })
}
