import type { Decision } from '@/features/eventRequests/api'
import type { FieldErrors } from '@/lib/api'

import { MISSING_MESSAGE } from './eventRequestRules'

/**
 * The backend's checks on the review actions' bodies, worded as marshmallow words them
 * (events/schemas.py DecideEventRequestSchema; common/validation.py not_blank; ADR-0028). Each
 * field is checked on its own and every message is reported at once.
 */

const NOT_NULL_MESSAGE = 'Field may not be null.'
const NOT_A_STRING_MESSAGE = 'Not a valid string.'
const BLANK_MESSAGE = 'Must not be blank.'
const UNKNOWN_FIELD_MESSAGE = 'Unknown field.'
const OUTCOME_MESSAGE = 'Outcome must be approved or rejected.'
const DECISION_FIELDS: readonly string[] = ['outcome', 'reason']

/** One of the two outcomes a decision may have. */
function isOutcome(value: unknown): value is Decision['outcome'] {
  return value === 'approved' || value === 'rejected'
}

/** Every field of `body` not in `allowed` is an unknown field. */
function unknownFieldErrors(
  body: Record<string, unknown>,
  allowed: readonly string[],
): FieldErrors {
  const errors: FieldErrors = {}
  for (const name of Object.keys(body)) {
    if (!allowed.includes(name)) {
      errors[name] = [UNKNOWN_FIELD_MESSAGE]
    }
  }
  return errors
}

/** What a text value that was sent is refused for: not text, or only spaces. */
function textErrors(value: unknown): string[] | undefined {
  if (typeof value !== 'string') {
    return [NOT_A_STRING_MESSAGE]
  }
  if (value.trim() === '') {
    return [BLANK_MESSAGE]
  }
  return undefined
}

function outcomeErrors(body: Record<string, unknown>): string[] | undefined {
  if (!('outcome' in body)) {
    return [MISSING_MESSAGE]
  }
  if (body.outcome === null) {
    return [NOT_NULL_MESSAGE]
  }
  if (!isOutcome(body.outcome)) {
    return [OUTCOME_MESSAGE]
  }
  return undefined
}

/** A decision as the backend loads it: the reason trimmed, or null when none was sent. */
export interface LoadedDecision {
  outcome: Decision['outcome']
  reason: string | null
}

/**
 * A decision's body, loaded, or what it is refused for. The reason may be left out or null
 * here: whether one is needed depends on the request, so the handler checks that afterwards.
 */
export function loadDecision(
  body: Record<string, unknown>,
): { decision: LoadedDecision } | { errors: FieldErrors } {
  const errors = unknownFieldErrors(body, DECISION_FIELDS)
  const outcome = outcomeErrors(body)
  if (outcome !== undefined) {
    errors.outcome = outcome
  }
  const { reason } = body
  if (reason !== undefined && reason !== null) {
    const reasonErrors = textErrors(reason)
    if (reasonErrors !== undefined) {
      errors.reason = reasonErrors
    }
  }
  // isOutcome again only tells TypeScript what outcomeErrors already checked.
  if (Object.keys(errors).length > 0 || !isOutcome(body.outcome)) {
    return { errors }
  }
  return {
    decision: { outcome: body.outcome, reason: typeof reason === 'string' ? reason.trim() : null },
  }
}
