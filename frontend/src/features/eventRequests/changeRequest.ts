import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import type { EventRequestStatus } from '@/config/eventStatus'
import { formText } from '@/features/auth/formText'

import type { ChangeRequestDetails, ChangeRequestStatus, EventRecord, RequestedChange } from './api'
import { differingFields } from './eventEdit'
import { fieldLabel, shownValue } from './eventHistory'
import type { Fact } from './eventHistory'

/**
 * The organiser's change request (SCRUM-56, ADR-0126): what its form sends, and how the record
 * words a request. Whether a request is allowed, and whether its values are, is the backend's to
 * say; the form is offered only in the statuses the backend takes one in.
 */

/**
 * The statuses the backend takes a change request in: every one from Submitted to Confirmed
 * (SCRUM-56 AC1).
 */
export const CHANGE_REQUESTABLE_STATUSES: readonly EventRequestStatus[] = [
  EVENT_REQUEST_STATUS.SUBMITTED,
  EVENT_REQUEST_STATUS.UNDER_REVIEW,
  EVENT_REQUEST_STATUS.AWAITING_CLARIFICATION,
  EVENT_REQUEST_STATUS.APPROVED,
  EVENT_REQUEST_STATUS.SAFETY_REVIEW,
  EVENT_REQUEST_STATUS.CONFIRMED,
]

/** What a change request can ask for: the date, times, size, requirements and programme (AC2). */
const REQUESTABLE_FIELDS = [
  'proposed_date',
  'end_date',
  'start_time',
  'end_time',
  'expected_attendance',
  'venue_requirements',
  'equipment_requirements',
  'programme_notes',
] as const

type RequestableField = (typeof REQUESTABLE_FIELDS)[number]

/**
 * What a record carries to show its change requests: the event's reference, the requests, what
 * each field a request can ask for holds now, and the venue arrangements the coordinator reviews
 * them against. The organiser's, the coordinator's and the staff record all do (SCRUM-56 AC4,
 * SCRUM-57 AC1, AC6).
 */
export type ChangeableRecord = Pick<
  EventRecord,
  'reference' | 'change_requests' | 'venue_arrangements' | RequestableField
>

export const CHANGE_REQUEST_STATUS_LABEL: Record<ChangeRequestStatus, string> = {
  pending: 'Pending',
  approved: 'Approved',
  rejected: 'Rejected',
  withdrawn: 'Withdrawn',
}

/** What the form asks for on `record`: each requestable field that differs from it, and why. */
export function requestedChange(form: FormData, record: EventRecord): ChangeRequestDetails {
  return {
    ...differingFields(form, record, REQUESTABLE_FIELDS),
    reason: formText(form, 'reason'),
  }
}

function isRequestable(field: string): field is RequestableField {
  return (REQUESTABLE_FIELDS as readonly string[]).includes(field)
}

/** One requested change as the record shows it, e.g. "Start time": "9:00 am → 10:30 am". */
export function describeRequestedChange(change: RequestedChange): Fact {
  const { field } = change
  const from = shownValue(field, change.previous_value)
  const to = shownValue(field, change.requested_value)
  return { label: fieldLabel(field), value: `${from} → ${to}` }
}

/**
 * One requested change beside what the event holds now, for the coordinator deciding it, e.g.
 * "Start time": "9:00 am now → 10:30 am" (SCRUM-57 AC1). A later edit may have moved the value
 * since the request was raised; approving is then the backend's to refuse (AC8).
 */
export function describeAgainstNow(change: RequestedChange, record: ChangeableRecord): Fact {
  const { field } = change
  const now = isRequestable(field) ? record[field] : null
  const to = shownValue(field, change.requested_value)
  return { label: fieldLabel(field), value: `${shownValue(field, now)} now → ${to}` }
}
