import type { EventRequestStatus } from '@/config/eventStatus'
import { apiRequest } from '@/lib/api'

import type { ChecklistItem, SafetyOutcome } from './constants'

/** The Safety Officer's endpoints: backend/app/modules/events/routes.py (SCRUM-97, SCRUM-98). */
const SAFETY_PATHS = {
  AWAITING: '/api/events/requests/awaiting-safety-review',
  outcomeFor: (reference: string) =>
    `/api/events/requests/${encodeURIComponent(reference)}/safety-outcome`,
} as const

/** The event itself: its name, when it is on, its status, and the needs under review. */
export interface SafetyReviewEventDetails {
  reference: string
  name: string
  /** Business-time dates and times with no offset, e.g. "2026-11-12" and "09:00:00". */
  proposed_date: string
  end_date: string | null
  start_time: string
  end_time: string
  status: EventRequestStatus
  expected_attendance: number
  accessibility_needs: string | null
}

/** A venue the event has booked, with what the Safety Officer reviews (SCRUM-97 AC6). */
export interface SafetyReviewVenue {
  name: string
  capacity: number
  /** The room layouts the venue supports, e.g. "theatre". */
  layouts: string[]
  facilities: string[]
  accessibility_features: string[]
  /** ISO date-times with an offset, in business time: the period the venue is booked for. */
  starts_at: string
  ends_at: string
}

/** Technical Support's answer to an equipment request (EquipmentLineStatus in the backend). */
export type EquipmentStatus = 'requested' | 'fulfilled' | 'partially_fulfilled' | 'unavailable'

/** An equipment request with Technical Support's outcome. */
export interface SafetyReviewEquipment {
  equipment_type_name: string
  quantity: number
  notes: string | null
  status: EquipmentStatus
  provided_quantity: number | null
  outcome_note: string | null
}

/** One event in Safety Review, as the Safety Officer's list sends it. */
export interface AwaitingSafetyReview {
  event: SafetyReviewEventDetails
  venues: SafetyReviewVenue[]
  equipment: SafetyReviewEquipment[]
}

export interface AwaitingSafetyReviewList {
  /** Soonest event first. */
  events: AwaitingSafetyReview[]
  /** Only present when the list is empty. */
  message?: string
}

export type SafetyChecklist = Record<ChecklistItem, string>

export interface RecordSafetyOutcomeInput {
  reference: string
  outcome: SafetyOutcome
  checklist: SafetyChecklist
  /** Required unless approving; the backend says so when it is missing. */
  reason?: string
}

/**
 * The event after the outcome: still in Safety Review after an approval, back at Approved
 * otherwise. The backend sends the request's other fields too.
 */
export interface RecordedSafetyOutcome {
  reference: string
  name: string
  status: EventRequestStatus
}

export const safetyKeys = {
  all: ['safety'] as const,
  awaiting: () => [...safetyKeys.all, 'awaiting'] as const,
  /** Marks the outcome mutations, so the page can show the latest one recorded. */
  outcome: () => [...safetyKeys.all, 'outcome'] as const,
}

export function fetchAwaitingSafetyReview(): Promise<AwaitingSafetyReviewList> {
  return apiRequest<AwaitingSafetyReviewList>(SAFETY_PATHS.AWAITING)
}

/** Record the Safety Officer's outcome, checklist and reason for an event in Safety Review. */
export function recordSafetyOutcome({
  reference,
  ...body
}: RecordSafetyOutcomeInput): Promise<RecordedSafetyOutcome> {
  return apiRequest<RecordedSafetyOutcome>(SAFETY_PATHS.outcomeFor(reference), {
    method: 'POST',
    body,
  })
}
