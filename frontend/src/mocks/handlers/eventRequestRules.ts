import type { EventRequestDetails } from '@/features/eventRequests/api'
import type { FieldErrors } from '@/lib/api'

import { MOCK_TODAY } from './catalogueFixtures'

/**
 * The backend's checks on an event request, worded as it words them (SCRUM-19, SCRUM-20,
 * ADR-0001 to ADR-0003, ADR-0024). A draft needs only a name, and each other field it sends is
 * checked on its own; a submission needs every required field, a date that isn't in the past
 * and an end after the start. The mock's "today" is MOCK_TODAY, as the catalogue's is.
 */

export const MISSING_MESSAGE = 'Missing data for required field.'
const NAME_MAX_LENGTH = 200

/** Every field the organiser may send; anything else is an unknown field. */
export const DETAIL_FIELDS: readonly (keyof EventRequestDetails)[] = [
  'name',
  'purpose',
  'description',
  'proposed_date',
  'end_date',
  'start_time',
  'end_time',
  'expected_attendance',
  'venue_requirements',
  'accessibility_needs',
  'equipment_requirements',
  'registration_required',
]

const REQUIRED_TO_SUBMIT: readonly (keyof EventRequestDetails)[] = [
  'name',
  'proposed_date',
  'start_time',
  'end_time',
  'expected_attendance',
]

/** A time as the backend shows it: "19:00" becomes "19:00:00". */
export function withSeconds(time: string): string {
  return time.length === 5 ? `${time}:00` : time
}

function isPresent(value: unknown): boolean {
  return value !== undefined && value !== null
}

/** The rules each field has whenever it is sent: unknown fields, the name and the attendance. */
function eachFieldErrors(body: Record<string, unknown>): FieldErrors {
  const errors: FieldErrors = {}
  for (const name of Object.keys(body)) {
    if (!(DETAIL_FIELDS as readonly string[]).includes(name)) {
      errors[name] = ['Unknown field.']
    }
  }
  if ('name' in body) {
    const name = typeof body.name === 'string' ? body.name : ''
    if (name.trim() === '') {
      errors.name = ['Event name must not be blank.']
    } else if (name.trim().length > NAME_MAX_LENGTH) {
      errors.name = [`Event name must be at most ${NAME_MAX_LENGTH} characters.`]
    }
  }
  const attendance = body.expected_attendance
  if (typeof attendance === 'number' && attendance < 1) {
    errors.expected_attendance = ['Expected attendance must be at least 1.']
  }
  return errors
}

/** What saving a new draft is refused for: a missing or blank name, or a bad field. */
export function draftErrors(body: Record<string, unknown>): FieldErrors {
  const errors = eachFieldErrors(body)
  if (!('name' in body)) {
    errors.name = [MISSING_MESSAGE]
  }
  return errors
}

/** What changing a draft is refused for: only the fields actually sent are checked. */
export function draftChangeErrors(body: Record<string, unknown>): FieldErrors {
  return eachFieldErrors(body)
}

/** What submitting is refused for, the way POST /api/events/requests checks it. */
export function submissionErrors(body: Record<string, unknown>): FieldErrors {
  const errors = eachFieldErrors(body)
  for (const name of REQUIRED_TO_SUBMIT) {
    if (!isPresent(body[name])) {
      errors[name] = [MISSING_MESSAGE]
    }
  }
  // A field rule, so it is reported alongside any missing field (ADR-0001).
  if (isPresent(body.proposed_date) && String(body.proposed_date) < MOCK_TODAY) {
    errors.proposed_date = ['Proposed date cannot be in the past.']
  }
  // The rules comparing two fields run only once every field has passed its own (ADR-0002).
  if (Object.keys(errors).length > 0) {
    return errors
  }

  const proposedDate = String(body.proposed_date)
  const endDate = isPresent(body.end_date) ? String(body.end_date) : proposedDate
  if (endDate < proposedDate) {
    return { end_date: ['End date cannot be before the proposed date.'] }
  }
  const starts = `${proposedDate}T${withSeconds(String(body.start_time))}`
  const ends = `${endDate}T${withSeconds(String(body.end_time))}`
  if (ends <= starts) {
    return { end_time: ['Event must end after it starts.'] }
  }
  return {}
}
