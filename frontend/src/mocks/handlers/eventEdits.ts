import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'

import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import type { EventRequestStatus } from '@/config/eventStatus'
import type { EventHistoryEntry, EventRequest, FieldChange } from '@/features/eventRequests/api'
import type { FieldErrors } from '@/lib/api'

import { errorResponse, readBody, validationError } from '../responses'

import { flagArrangementsAfterChange } from './booking'
import { MOCK_NOW, MOCK_TODAY } from './catalogueFixtures'
import { NOTHING_PLANNED } from './eventPlanningFixtures'
import { addToHistory } from './eventRecordSections'
import { withSeconds } from './eventRequestRules'
import { assignedOrRefusal } from './eventRequests'
import { positiveWholeNumberError } from './equipmentValidation'
import type { MockEventRequest } from './eventRequestFixtures'
import { FLAGGABLE_STATUSES, reassessmentFlagsFor } from './reassessmentRules'
import type { SignificantChange } from './reassessmentRules'

/**
 * The assigned coordinator's edit (PATCH /api/events/requests/<reference>; SCRUM-33, ADR-0025):
 * only the fields sent change, each checked as the backend checks it, and each change is
 * answered and written to the history, significant or not; a significant change withdraws a
 * safety approval (AC7), and each venue arrangement it affects is flagged, in the booking mock and
 * in the planning the gates count (AC6, ADR-0094); in Safety Review, a flag sends the event back
 * to Approved (AC9, ADR-0107). The Safety Officers' notice isn't raised: the notifications mock
 * serves only its seeded notices. Checks run in the backend's order:
 * the coordinator's own event (404), a status that can be edited (409: every status before
 * Confirmed, and a Confirmed event is pointed to a change request; AC8, ADR-0101), then the
 * fields (400). The planning notes are kept here: the organiser's record and the staff record
 * read them, and the coordinator's own record doesn't (ADR-0095, ADR-0104).
 */

const REQUESTS_PATH = '/api/events/requests'
const NOT_EDITABLE_MESSAGE =
  'An event request can only be edited before it is confirmed, and not once it is rejected or cancelled.'
const CONFIRMED_NOT_EDITABLE_MESSAGE =
  'A confirmed event can only be changed through a change request.'
const NOT_NULL_MESSAGE = 'Field may not be null.'
/** Every status before Confirmed (`EDITABLE_STATUSES`, SCRUM-33 AC8, ADR-0101). */
const EDITABLE_STATUSES: readonly EventRequestStatus[] = [
  EVENT_REQUEST_STATUS.SUBMITTED,
  EVENT_REQUEST_STATUS.UNDER_REVIEW,
  EVENT_REQUEST_STATUS.AWAITING_CLARIFICATION,
  EVENT_REQUEST_STATUS.APPROVED,
  EVENT_REQUEST_STATUS.SAFETY_REVIEW,
]
/** Where a withdrawn safety approval sends an event back to Approved (ADR-0087). */
const RETURNED_TO_PLANNING_ON_WITHDRAWAL: readonly EventRequestStatus[] = [
  EVENT_REQUEST_STATUS.SAFETY_REVIEW,
  EVENT_REQUEST_STATUS.CONFIRMED,
]
/** Every field the edit takes, in the backend's order (EditEventRequestSchema.Meta.fields). */
const EDITABLE_FIELDS = [
  'description',
  'programme_notes',
  'accessibility_needs',
  'internal_planning_notes',
  'proposed_date',
  'end_date',
  'start_time',
  'end_time',
  'expected_attendance',
  'venue_requirements',
  'equipment_requirements',
] as const
type EditableField = (typeof EDITABLE_FIELDS)[number]
/** Fields that can't be emptied: when and how big the event is. */
const NOT_NULL_FIELDS: readonly string[] = [
  'proposed_date',
  'end_date',
  'start_time',
  'end_time',
  'expected_attendance',
]
const SIGNIFICANT_FIELDS: readonly string[] = [
  ...NOT_NULL_FIELDS,
  'venue_requirements',
  'equipment_requirements',
]
/** The fields that say when the event happens (`_TIMING_FIELDS`). */
const TIMING_FIELDS: readonly string[] = ['proposed_date', 'end_date', 'start_time', 'end_time']
const DAY_MS = 24 * 60 * 60_000
/** What marshmallow reads as a date ("2026-11-12") and a time ("09:00" or "09:00:00"). */
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/
const TIME_PATTERN = /^([01]\d|2[0-3]):[0-5]\d(:[0-5]\d)?$/
/** A time with an offset, which the backend reads and then refuses (ADR-0002). */
const TIME_WITH_OFFSET_PATTERN = /^([01]\d|2[0-3]):[0-5]\d(:[0-5]\d)?(Z|[+-]\d{2}:\d{2})$/

type Values = Partial<Record<EditableField, string | number | null>>

/** Internal planning notes by reference; none until an edit sets them. Reset per test. */
let internalNotes: Record<string, string | null> = {}

export function resetMockEventEdits(): void {
  internalNotes = {}
}

/** The event's planning notes as last saved, or null: staff and the organiser read them. */
export function internalNotesOf(reference: string): string | null {
  return internalNotes[reference] ?? null
}

function isEditableField(name: string): name is EditableField {
  return (EDITABLE_FIELDS as readonly string[]).includes(name)
}

/** `date` moved by `days`, both "2026-11-12". */
function addDays(date: string, days: number): string {
  return new Date(Date.parse(`${date}T00:00:00Z`) + days * DAY_MS).toISOString().slice(0, 10)
}

function daysBetween(from: string, to: string): number {
  return Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / DAY_MS)
}

function timeError(value: unknown): string | undefined {
  if (typeof value === 'string' && TIME_PATTERN.test(value)) {
    return undefined
  }
  if (typeof value === 'string' && TIME_WITH_OFFSET_PATTERN.test(value)) {
    return 'Time must not include a timezone offset.'
  }
  return 'Not a valid time.'
}

/** What is wrong with one sent value, in marshmallow's words, or undefined when nothing is. */
function valueError(name: EditableField, value: unknown): string | undefined {
  if (name === 'expected_attendance') {
    return positiveWholeNumberError(value, 'Expected attendance must be at least 1.')
  }
  if (value === null) {
    return NOT_NULL_FIELDS.includes(name) ? NOT_NULL_MESSAGE : undefined
  }
  if (name === 'proposed_date' || name === 'end_date') {
    return typeof value === 'string' && DATE_PATTERN.test(value) ? undefined : 'Not a valid date.'
  }
  if (name === 'start_time' || name === 'end_time') {
    return timeError(value)
  }
  return typeof value === 'string' ? undefined : 'Not a valid string.'
}

/** Each field's own rules: unknown fields, types, nulls, the attendance and the past date. */
function fieldErrors(body: Record<string, unknown>): FieldErrors {
  const errors: FieldErrors = {}
  for (const [name, value] of Object.entries(body)) {
    const error = isEditableField(name) ? valueError(name, value) : 'Unknown field.'
    if (error !== undefined) {
      errors[name] = [error]
    }
  }
  const proposedDate = body.proposed_date
  const isValidDate = errors.proposed_date === undefined && typeof proposedDate === 'string'
  if (isValidDate && proposedDate < MOCK_TODAY) {
    errors.proposed_date = ['Proposed date cannot be in the past.']
  }
  return errors
}

/** What the backend saves from the body: text trimmed, blank as null, times with seconds. */
function loadedValues(body: Record<string, unknown>): Values {
  const values: Values = {}
  for (const field of EDITABLE_FIELDS) {
    const value = body[field]
    if (!(field in body) || value === undefined) {
      continue
    }
    if (typeof value === 'string' && (field === 'start_time' || field === 'end_time')) {
      values[field] = withSeconds(value)
    } else if (typeof value === 'string') {
      values[field] = value.trim() === '' ? null : value.trim()
    } else if (typeof value === 'number' || value === null) {
      values[field] = value
    }
  }
  return values
}

/** A date moved on its own takes the end date with it, keeping the event's length. */
function withEndDate(values: Values, request: EventRequest): Values {
  if (!('proposed_date' in values) || 'end_date' in values) {
    return values
  }
  const start = String(request.proposed_date)
  const length = daysBetween(start, String(request.end_date))
  return { ...values, end_date: addDays(String(values.proposed_date), length) }
}

/** The window rule on the values the event would have (ADR-0002), or null when it holds. */
function windowErrors(values: Values, request: EventRequest): FieldErrors | null {
  const proposedDate = String(values.proposed_date ?? request.proposed_date)
  const endDate = String(values.end_date ?? request.end_date)
  if (endDate < proposedDate) {
    return { end_date: ['End date cannot be before the proposed date.'] }
  }
  const starts = `${proposedDate}T${String(values.start_time ?? request.start_time)}`
  const ends = `${endDate}T${String(values.end_time ?? request.end_time)}`
  if (ends <= starts) {
    return { end_time: ['Event must end after it starts.'] }
  }
  return null
}

function currentValue(stored: MockEventRequest, field: EditableField) {
  if (field === 'programme_notes') {
    return stored.record.programme_notes
  }
  if (field === 'internal_planning_notes') {
    return internalNotesOf(stored.request.reference)
  }
  return stored.request[field]
}

/** Save each value that differs from what is saved, and say what changed. */
function applyChanges(stored: MockEventRequest, values: Values): FieldChange[] {
  const changes: FieldChange[] = []
  for (const [name, value] of Object.entries(values)) {
    if (!isEditableField(name)) {
      continue
    }
    const previous = currentValue(stored, name)
    const next = value ?? null
    if (previous === next) {
      continue
    }
    changes.push({
      field: name,
      previous_value: previous,
      new_value: next,
      significant: SIGNIFICANT_FIELDS.includes(name),
    })
    if (name === 'programme_notes') {
      stored.record = { ...stored.record, programme_notes: value === null ? null : String(value) }
    } else if (name === 'internal_planning_notes') {
      internalNotes[stored.request.reference] = value === null ? null : String(value)
    } else {
      stored.request = { ...stored.request, [name]: next }
    }
  }
  return changes
}

/** One field_changed entry per change, by the coordinator, at the mock's "now". */
function historyOf(changes: FieldChange[], actorName: string): EventHistoryEntry[] {
  return changes.map((change) => ({
    kind: 'field_changed',
    occurred_at: MOCK_NOW,
    actor_name: actorName,
    details: { ...change },
  }))
}

/**
 * Whether the Safety Officer's approval stands (`has_safety_approval`), as the event's planning
 * says. A Confirmed event, which always has one, can't be edited (AC8), so it never gets here.
 */
function hasSafetyApproval(stored: MockEventRequest): boolean {
  return stored.planning?.isSafetyApproved ?? false
}

/**
 * A significant change withdraws the safety approval (SCRUM-33 AC7, `withdraw_safety_approval`):
 * the event goes back to Approved for a new check, and the withdrawal, naming the significant
 * fields, is the entry this returns. An event with no approval, or a change that isn't
 * significant, withdraws nothing.
 */
function withdrawnSafetyApproval(
  stored: MockEventRequest,
  changes: FieldChange[],
  actorName: string,
): EventHistoryEntry[] {
  const significantFields = changes
    .filter((change) => change.significant)
    .map((change) => change.field)
  if (significantFields.length === 0 || !hasSafetyApproval(stored)) {
    return []
  }
  stored.planning = { ...(stored.planning ?? NOTHING_PLANNED), isSafetyApproved: false }
  if (RETURNED_TO_PLANNING_ON_WITHDRAWAL.includes(stored.request.status)) {
    stored.request = { ...stored.request, status: EVENT_REQUEST_STATUS.APPROVED }
  }
  return [
    {
      kind: 'safety_approval_withdrawn',
      occurred_at: MOCK_NOW,
      actor_name: actorName,
      details: { significant_fields: significantFields },
    },
  ]
}

/** When an event starts, as milliseconds, from its date ("2026-11-12") and time ("09:00:00"). */
function startInstant(date: unknown, time: unknown): number {
  return Date.parse(`${String(date)}T${withSeconds(String(time))}+08:00`)
}

/**
 * How far `changes` moved the event's start, in milliseconds, which the booking mock moves the
 * flagged bookings' pre-filled period by (SCRUM-59 AC2). `request` already holds the new values.
 */
function startMovedBy(changes: FieldChange[], request: MockEventRequest['request']): number {
  let dateBefore: unknown = request.proposed_date
  let timeBefore: unknown = request.start_time
  for (const change of changes) {
    if (change.field === 'proposed_date') {
      dateBefore = change.previous_value
    }
    if (change.field === 'start_time') {
      timeBefore = change.previous_value
    }
  }
  const startsNow = startInstant(request.proposed_date, request.start_time)
  return startsNow - startInstant(dateBefore, timeBefore)
}

/** What `changes` did to the event's venue arrangements, as `_flag_venue_arrangements` sees it. */
function significantChangeOf(
  changes: FieldChange[],
  previousAttendance: number,
  stored: MockEventRequest,
): SignificantChange {
  const changedFields = changes.map((change) => change.field)
  return {
    timingChanged: changedFields.some((field) => TIMING_FIELDS.includes(field)),
    venueRequirementsChanged: changedFields.includes('venue_requirements'),
    previousAttendance,
    newAttendance: Number(stored.request.expected_attendance),
    startMovedByMs: startMovedBy(changes, stored.request),
  }
}

/**
 * Flag each live arrangement the gates count that `change` affects (SCRUM-33 AC6); a withdrawn or
 * rejected one has nothing to lose, and an event with nothing planned has none. Says whether it
 * flagged any.
 */
function flagPlannedArrangements(stored: MockEventRequest, change: SignificantChange): boolean {
  if (stored.planning === undefined) {
    return false
  }
  let flaggedAny = false
  const arrangements = stored.planning.arrangements.map((arrangement) => {
    if (!FLAGGABLE_STATUSES.includes(arrangement.status)) {
      return arrangement
    }
    const flags = reassessmentFlagsFor(arrangement, change)
    if (flags.length > 0) {
      flaggedAny = true
    }
    return { ...arrangement, reassessmentFlags: [...arrangement.reassessmentFlags, ...flags] }
  })
  stored.planning = { ...stored.planning, arrangements }
  return flaggedAny
}

/**
 * An event in Safety Review whose change flagged an arrangement no longer meets the Safety Review
 * rules, so it goes back to Approved (SCRUM-33 AC9, `_return_to_approved`, ADR-0107). One a
 * withdrawn approval already sent back stays where it is.
 */
function returnToApproved(stored: MockEventRequest): void {
  if (stored.request.status === EVENT_REQUEST_STATUS.SAFETY_REVIEW) {
    stored.request = { ...stored.request, status: EVENT_REQUEST_STATUS.APPROVED }
  }
}

export const eventEditHandlers: RequestHandler[] = [
  http.patch(`${REQUESTS_PATH}/:reference`, async ({ request, params }) => {
    const found = assignedOrRefusal(request, params.reference)
    if ('refusal' in found) {
      return found.refusal
    }
    const { coordinator, stored } = found
    if (stored.request.status === EVENT_REQUEST_STATUS.CONFIRMED) {
      return errorResponse(409, 'request_not_editable', CONFIRMED_NOT_EDITABLE_MESSAGE)
    }
    if (!EDITABLE_STATUSES.includes(stored.request.status)) {
      return errorResponse(409, 'request_not_editable', NOT_EDITABLE_MESSAGE)
    }
    const body = await readBody(request)
    const errors = fieldErrors(body)
    if (Object.keys(errors).length > 0) {
      return validationError(errors)
    }
    const values = withEndDate(loadedValues(body), stored.request)
    const refused = windowErrors(values, stored.request)
    if (refused !== null) {
      return validationError(refused)
    }

    const attendanceBefore = Number(stored.request.expected_attendance)
    const changes = applyChanges(stored, values)
    const change = significantChangeOf(changes, attendanceBefore, stored)
    const flaggedAny = flagPlannedArrangements(stored, change)
    flagArrangementsAfterChange(stored.request.reference, change)
    addToHistory(stored.request.reference, [
      ...historyOf(changes, coordinator.full_name),
      ...withdrawnSafetyApproval(stored, changes, coordinator.full_name),
    ])
    if (flaggedAny) {
      returnToApproved(stored)
    }
    return HttpResponse.json({
      ...stored.request,
      programme_notes: stored.record.programme_notes,
      internal_planning_notes: internalNotesOf(stored.request.reference),
      changes,
    })
  }),
]
