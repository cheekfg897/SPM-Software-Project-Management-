import type { RegistrationChanges } from '@/features/eventRequests/api'
import type { FieldErrors } from '@/lib/api'

/**
 * The backend's checks on a change to an event's registration settings, worded as marshmallow
 * words them (events/schemas.py UpdateRegistrationSettingsSchema, common/fields.py WholeNumber;
 * ADR-0043). Each field is checked on its own, only when sent, and every message is reported at
 * once.
 */

const REGISTRATION_FIELDS: readonly string[] = ['registration_enabled', 'registration_capacity']
const UNKNOWN_FIELD_MESSAGE = 'Unknown field.'
const NOT_NULL_MESSAGE = 'Field may not be null.'
const NOT_A_BOOLEAN_MESSAGE = 'Not a valid boolean.'
const NOT_AN_INTEGER_MESSAGE = 'Not a valid integer.'
/** The largest value a Postgres INTEGER column holds, as the schema bounds the capacity. */
const LARGEST_CAPACITY = 2_147_483_647
const CAPACITY_RANGE_MESSAGE = `Capacity must be between 1 and ${LARGEST_CAPACITY}.`

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

/** A change's body, loaded, or what it is refused for. Only what is sent is in the change. */
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
  return { changes }
}
