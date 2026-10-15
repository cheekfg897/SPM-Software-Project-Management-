import { apiRequest } from '@/lib/api'

import type { EventRequestStatus } from '@/config/eventStatus'

const EVENT_REQUEST_PATHS = {
  MINE: '/api/events/requests',
} as const

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
}

/** The organiser's client organisation's event requests and their own drafts, newest first. */
export function fetchMyEventRequests(): Promise<EventRequestList> {
  return apiRequest<EventRequestList>(EVENT_REQUEST_PATHS.MINE)
}
