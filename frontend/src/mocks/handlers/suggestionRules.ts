import type { BookingRequest } from '@/features/booking/api'
import type { FieldErrors } from '@/lib/api'

import { instantOf } from './venueBlockRules'
import { currentMockVenues } from './venues'

/**
 * The alternative Venue Staff may suggest when they reject a request (SCRUM-70, ADR-0123), checked
 * as backend/app/modules/venue/schemas.py (its shape) and services.py (its rules) check it, with
 * the same messages.
 */

const ONLY_WHEN_REJECTING_MESSAGE = 'An alternative can only be suggested when rejecting a request.'
const NOT_ACTIVE_MESSAGE = 'The suggested venue must be an active venue.'
const PERIOD_LOCKED_MESSAGE =
  'A replacement keeps the period of the booking it replaces, so only another venue can be suggested.'
const NOT_WHOLE_MESSAGE = 'A suggested period needs both a start and an end.'
const ENDS_BEFORE_START_MESSAGE = 'suggested_ends_at must be after suggested_starts_at.'
const NOT_A_DATE_TIME_MESSAGE = 'Not a valid datetime.'
const PERIOD_FIELDS = ['suggested_starts_at', 'suggested_ends_at'] as const
/** The parts of a suggestion, in the order the backend reports them. */
const SUGGESTION_FIELDS = ['suggested_venue_id', ...PERIOD_FIELDS] as const

/** A suggestion as the request keeps it: each part null when it wasn't given. */
export type Suggestion = Pick<
  BookingRequest,
  'suggested_venue_id' | 'suggested_starts_at' | 'suggested_ends_at'
>

/** No suggestion, as every request starts. */
export const NO_SUGGESTION: Suggestion = {
  suggested_venue_id: null,
  suggested_starts_at: null,
  suggested_ends_at: null,
}

function venueIdError(value: unknown): string | null {
  if (typeof value !== 'number' || !Number.isInteger(value)) {
    return 'Not a valid integer.'
  }
  return value < 1 ? 'suggested_venue_id must be a positive number.' : null
}

/** Each period part sent that isn't a date and time: the fields' own messages. */
function periodFieldErrors(startsAt: unknown, endsAt: unknown): FieldErrors {
  const errors: FieldErrors = {}
  if (startsAt !== undefined && instantOf(startsAt) === null) {
    errors.suggested_starts_at = [NOT_A_DATE_TIME_MESSAGE]
  }
  if (endsAt !== undefined && instantOf(endsAt) === null) {
    errors.suggested_ends_at = [NOT_A_DATE_TIME_MESSAGE]
  }
  return errors
}

/** The schema-wide message for a period that isn't whole or doesn't end after it starts. */
function periodSchemaErrors(startsAt: unknown, endsAt: unknown): FieldErrors {
  if (startsAt === undefined && endsAt === undefined) {
    return {}
  }
  if (startsAt === undefined) {
    return { suggested_starts_at: [NOT_WHOLE_MESSAGE] }
  }
  if (endsAt === undefined) {
    return { suggested_ends_at: [NOT_WHOLE_MESSAGE] }
  }
  const starts = instantOf(startsAt)
  const ends = instantOf(endsAt)
  if (starts !== null && ends !== null && ends <= starts) {
    return { suggested_ends_at: [ENDS_BEFORE_START_MESSAGE] }
  }
  return {}
}

/**
 * DecideBookingRequestSchema's messages about a suggestion's shape: a venue id that isn't a whole
 * number from 1, a period part that isn't a date and time, and then, only if no field was refused
 * (marshmallow skips a `@validates_schema` check after a field error), a period that isn't whole
 * or doesn't end after it starts. A part sent as null counts as not sent, as the schema's
 * `load_default=None` makes it.
 */
export function suggestionShapeErrors(body: Record<string, unknown>): FieldErrors {
  const startsAt = body.suggested_starts_at ?? undefined
  const endsAt = body.suggested_ends_at ?? undefined
  const errors = periodFieldErrors(startsAt, endsAt)
  const venueId = body.suggested_venue_id ?? undefined
  if (venueId !== undefined) {
    const message = venueIdError(venueId)
    if (message !== null) {
      errors.suggested_venue_id = [message]
    }
  }
  if (Object.keys(errors).length > 0) {
    return errors
  }
  return periodSchemaErrors(startsAt, endsAt)
}

/** The suggestion a body whose shape was checked carries. */
export function suggestionIn(body: Record<string, unknown>): Suggestion {
  return {
    suggested_venue_id:
      typeof body.suggested_venue_id === 'number' ? body.suggested_venue_id : null,
    suggested_starts_at:
      typeof body.suggested_starts_at === 'string' ? body.suggested_starts_at : null,
    suggested_ends_at: typeof body.suggested_ends_at === 'string' ? body.suggested_ends_at : null,
  }
}

function isActiveVenue(venueId: number): boolean {
  return currentMockVenues().some((venue) => venue.id === venueId && venue.is_active)
}

/** Each message on every field named. */
function onEach(fields: readonly string[], message: string): FieldErrors {
  const errors: FieldErrors = {}
  for (const field of fields) {
    errors[field] = [message]
  }
  return errors
}

/**
 * The backend's `_check_suggestion`: only a rejection carries one, the venue must be active, and
 * a replacement that `keepsItsPeriod` (its venue became unavailable, SCRUM-92) takes no period.
 */
export function suggestionRuleErrors(
  suggestion: Suggestion,
  outcome: 'approved' | 'rejected',
  keepsItsPeriod: boolean,
): FieldErrors {
  const given = SUGGESTION_FIELDS.filter((field) => suggestion[field] !== null)
  if (given.length === 0) {
    return {}
  }
  if (outcome !== 'rejected') {
    return onEach(given, ONLY_WHEN_REJECTING_MESSAGE)
  }
  const venueId = suggestion.suggested_venue_id
  if (venueId !== null && !isActiveVenue(venueId)) {
    return onEach(['suggested_venue_id'], NOT_ACTIVE_MESSAGE)
  }
  if (suggestion.suggested_starts_at !== null && keepsItsPeriod) {
    return onEach(PERIOD_FIELDS, PERIOD_LOCKED_MESSAGE)
  }
  return {}
}

/** The suggested venue's name, for the event record, or null when none was suggested. */
export function suggestedVenueName(suggestion: Suggestion): string | null {
  const venue = currentMockVenues().find((known) => known.id === suggestion.suggested_venue_id)
  return venue?.name ?? null
}
