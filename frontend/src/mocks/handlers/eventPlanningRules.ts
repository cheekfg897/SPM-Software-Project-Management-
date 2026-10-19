import type { RegistrationChanges } from '@/features/eventRequests/api'
import type { FieldErrors } from '@/lib/api'

/**
 * The backend's checks on a change to an event's registration settings, worded as marshmallow
 * words them (events/schemas.py UpdateRegistrationSettingsSchema, common/fields.py WholeNumber;
 * ADR-0043, ADR-0086). Each field is checked on its own, only when sent, and every message is
 * reported at once.
 */

const REGISTRATION_FIELDS: readonly string[] = [
  'registration_enabled',
  'registration_capacity',
  'withdrawal_cut_off',
]
const UNKNOWN_FIELD_MESSAGE = 'Unknown field.'
const NOT_NULL_MESSAGE = 'Field may not be null.'
const NOT_A_BOOLEAN_MESSAGE = 'Not a valid boolean.'
const NOT_AN_INTEGER_MESSAGE = 'Not a valid integer.'
/** The largest value a Postgres INTEGER column holds, as the schema bounds the capacity. */
const LARGEST_CAPACITY = 2_147_483_647
const CAPACITY_RANGE_MESSAGE = `Capacity must be between 1 and ${LARGEST_CAPACITY}.`
const NOT_A_DATE_TIME_MESSAGE = 'Not a valid datetime.'
/** Singapore's offset: a date-time sent without one is business time (ADR-0009). */
const BUSINESS_TIME_OFFSET = '+08:00'
const BUSINESS_TIME_OFFSET_MS = 8 * 60 * 60 * 1000
/**
 * The ISO 8601 date-times Python's `datetime.fromisoformat` reads, which marshmallow's DateTime
 * field uses: a date, then optionally a time (seconds and a fraction optional) and an offset.
 * Python also reads a few compact forms (`20261113T100000`); the mock refuses those, so it is
 * never more permissive than the backend.
 */
const DATE_TIME_PATTERN =
  /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d{1,6})?)?)?(Z|[+-]\d{2}:?\d{2})?$/

/** How far `offset` (`Z`, `+08:00` or `-0530`) is ahead of UTC, in milliseconds. */
function offsetMs(offset: string): number {
  if (offset === 'Z') {
    return 0
  }
  const sign = offset.startsWith('-') ? -1 : 1
  const digits = offset.slice(1).replace(':', '')
  const minutes = Number(digits.slice(0, 2)) * 60 + Number(digits.slice(2))
  return sign * minutes * 60 * 1000
}

/** The instant `value` names, or null when it isn't a date-time or names no real moment. */
function instantOf(value: string): number | null {
  const match = DATE_TIME_PATTERN.exec(value)
  if (match === null) {
    return null
  }
  const [, year, month, day, hour = '00', minute = '00', second = '00', offset] = match
  const writtenOut = `${year}-${month}-${day}T${hour}:${minute}:${second}`
  const asIfUtc = Date.parse(`${writtenOut}Z`)
  // A moment that doesn't exist (30 February, hour 25) either fails to parse or rolls over to
  // another one; Python refuses both, so the round trip must give back what was written.
  if (Number.isNaN(asIfUtc) || new Date(asIfUtc).toISOString().slice(0, 19) !== writtenOut) {
    return null
  }
  return asIfUtc - offsetMs(offset ?? BUSINESS_TIME_OFFSET)
}

/** An instant as the backend shows it: business time, with its offset (ADR-0009). */
export function asBusinessTime(instant: number): string {
  const shifted = new Date(instant + BUSINESS_TIME_OFFSET_MS).toISOString()
  return `${shifted.slice(0, 19)}${BUSINESS_TIME_OFFSET}`
}

/** What `registration_enabled` is refused for: null, or anything but true or false. */
function enabledErrors(value: unknown): string[] | undefined {
  if (value === null) {
    return [NOT_NULL_MESSAGE]
  }
  if (typeof value !== 'boolean') {
    return [NOT_A_BOOLEAN_MESSAGE]
  }
  return undefined
}

/** What `registration_capacity` is refused for: null, not a whole number, or out of range. */
function capacityErrors(value: unknown): string[] | undefined {
  if (value === null) {
    return [NOT_NULL_MESSAGE]
  }
  if (typeof value !== 'number' || !Number.isInteger(value)) {
    return [NOT_AN_INTEGER_MESSAGE]
  }
  if (value < 1 || value > LARGEST_CAPACITY) {
    return [CAPACITY_RANGE_MESSAGE]
  }
  return undefined
}

/** What `withdrawal_cut_off` is refused for: anything but null or a real date-time. */
function cutOffErrors(value: unknown): string[] | undefined {
  if (value === null) {
    return undefined
  }
  if (typeof value !== 'string' || instantOf(value) === null) {
    return [NOT_A_DATE_TIME_MESSAGE]
  }
  return undefined
}

/**
 * A change's body, loaded, or what it is refused for. Only what is sent is in the change; a
 * cut-off comes back in business time, or null to clear it.
 */
export function loadRegistrationChanges(
  body: Record<string, unknown>,
): { changes: RegistrationChanges } | { errors: FieldErrors } {
  const errors: FieldErrors = {}
  for (const name of Object.keys(body)) {
    if (!REGISTRATION_FIELDS.includes(name)) {
      errors[name] = [UNKNOWN_FIELD_MESSAGE]
    }
  }
  const { registration_enabled: enabled, registration_capacity: capacity } = body
  const enabledProblems = 'registration_enabled' in body ? enabledErrors(enabled) : undefined
  if (enabledProblems !== undefined) {
    errors.registration_enabled = enabledProblems
  }
  const capacityProblems = 'registration_capacity' in body ? capacityErrors(capacity) : undefined
  if (capacityProblems !== undefined) {
    errors.registration_capacity = capacityProblems
  }
  const cutOff = body.withdrawal_cut_off
  const cutOffProblems = 'withdrawal_cut_off' in body ? cutOffErrors(cutOff) : undefined
  if (cutOffProblems !== undefined) {
    errors.withdrawal_cut_off = cutOffProblems
  }
  if (Object.keys(errors).length > 0) {
    return { errors }
  }

  const changes: RegistrationChanges = {}
  // The typeof checks only tell TypeScript what the checks above already made sure of.
  if (typeof enabled === 'boolean') {
    changes.registration_enabled = enabled
  }
  if (typeof capacity === 'number') {
    changes.registration_capacity = capacity
  }
  if (cutOff === null) {
    changes.withdrawal_cut_off = null
  }
  const cutOffInstant = typeof cutOff === 'string' ? instantOf(cutOff) : null
  if (cutOffInstant !== null) {
    changes.withdrawal_cut_off = asBusinessTime(cutOffInstant)
  }
  return { changes }
}
