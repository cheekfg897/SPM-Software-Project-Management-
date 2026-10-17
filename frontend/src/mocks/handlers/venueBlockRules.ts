import { BUSINESS_UTC_OFFSET } from '@/config/time'
import type { FieldErrors } from '@/lib/api'

import { MOCK_TODAY } from './catalogueFixtures'
import { MISSING_MESSAGE } from './venueRules'

/**
 * The backend's checks on a block (BlockVenueSchema, SCRUM-34, ADR-0016) and on the calendar's
 * range (CalendarQuerySchema, SCRUM-26), worded as marshmallow words them. As in marshmallow,
 * the rules about the two times together only run once every field on its own is valid. The
 * mock's "today" is MOCK_TODAY, as the catalogue's is.
 */

const NOT_DATETIME_MESSAGE = 'Not a valid datetime.'
const REASON_MAX_LENGTH = 500
/** An ISO date-time, with or without seconds and an offset, as fields.DateTime takes it. */
const ISO_DATE_TIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?(Z|[+-]\d{2}:\d{2})?$/

/**
 * A date-time as milliseconds, or null if it isn't one. One without an offset is business time
 * (as_utc, ADR-0009).
 */
export function instantOf(value: unknown): number | null {
  if (typeof value !== 'string' || !ISO_DATE_TIME.test(value)) {
    return null
  }
  const hasOffset = /(Z|[+-]\d{2}:\d{2})$/.test(value)
  const instant = Date.parse(hasOffset ? value : `${value}${BUSINESS_UTC_OFFSET}`)
  return Number.isNaN(instant) ? null : instant
}

/** The field as an instant, or null with its message added to `errors`. */
function instantField(
  body: Record<string, unknown>,
  field: string,
  errors: FieldErrors,
): number | null {
  if (body[field] === undefined) {
    errors[field] = [MISSING_MESSAGE]
    return null
  }
  const instant = instantOf(body[field])
  if (instant === null) {
    errors[field] = [NOT_DATETIME_MESSAGE]
  }
  return instant
}

/** The business date an instant falls on, e.g. "2026-10-05". */
function businessDateOf(instant: number): string {
  return new Date(instant + 8 * 60 * 60_000).toISOString().slice(0, 10)
}

/** What blocking a venue is refused for (BlockVenueSchema). */
export function blockErrors(body: Record<string, unknown>): FieldErrors {
  const errors: FieldErrors = {}
  const start = instantField(body, 'start_time', errors)
  const end = instantField(body, 'end_time', errors)
  const reason = body.reason
  if (reason === undefined) {
    errors.reason = [MISSING_MESSAGE]
  } else if (typeof reason !== 'string') {
    errors.reason = ['Not a valid string.']
  } else if (reason.trim() === '') {
    errors.reason = ['Must not be blank.']
  } else if (reason.trim().length > REASON_MAX_LENGTH) {
    errors.reason = [`Reason must be at most ${REASON_MAX_LENGTH} characters.`]
  }
  if (Object.keys(errors).length > 0 || start === null || end === null) {
    return errors
  }
  const endMessages: string[] = []
  if (end <= start) {
    endMessages.push('end_time must be after start_time.')
  }
  if (businessDateOf(end) < MOCK_TODAY) {
    endMessages.push('Block cannot end before today.')
  }
  return endMessages.length > 0 ? { end_time: endMessages } : {}
}

/** What the calendar's range is refused for (CalendarQuerySchema). */
export function calendarRangeErrors(query: URLSearchParams): FieldErrors {
  const errors: FieldErrors = {}
  const params: Record<string, unknown> = {}
  for (const [name, value] of query.entries()) {
    if (name === 'range_start' || name === 'range_end') {
      params[name] = value
    } else {
      errors[name] = ['Unknown field.']
    }
  }
  const start = instantField(params, 'range_start', errors)
  const end = instantField(params, 'range_end', errors)
  if (Object.keys(errors).length > 0 || start === null || end === null) {
    return errors
  }
  return end <= start ? { range_end: ['range_end must be after range_start.'] } : {}
}
