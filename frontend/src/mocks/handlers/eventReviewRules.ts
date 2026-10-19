import type { Decision } from '@/features/eventRequests/api'
import type { FieldErrors } from '@/lib/api'

import { MISSING_MESSAGE } from './eventRequestRules'

/**
 * The backend's checks on the review actions' bodies, worded as marshmallow words them
 * (events/schemas.py DecideEventRequestSchema, RequestClarificationSchema,
 * ResubmitEventRequestSchema and RejectEventSchema; common/validation.py not_blank; ADR-0028,
 * ADR-0029, ADR-0093). Each field is checked on its own and every message is reported at once.
 */

const NOT_NULL_MESSAGE = 'Field may not be null.'
const NOT_A_STRING_MESSAGE = 'Not a valid string.'
const BLANK_MESSAGE = 'Must not be blank.'
const UNKNOWN_FIELD_MESSAGE = 'Unknown field.'
const OUTCOME_MESSAGE = 'Outcome must be approved or rejected.'
const DECISION_FIELDS: readonly string[] = ['outcome', 'reason']
const REJECTION_REASON_REQUIRED_MESSAGE = 'A reason is required to reject the event.'

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

/** What a required field is refused for when it is left out or null. */
function requiredErrors(body: Record<string, unknown>, field: string): string[] | undefined {
  if (!(field in body)) {
    return [MISSING_MESSAGE]
  }
  if (body[field] === null) {
    return [NOT_NULL_MESSAGE]
  }
  return undefined
}

function outcomeErrors(body: Record<string, unknown>): string[] | undefined {
  const required = requiredErrors(body, 'outcome')
  if (required !== undefined) {
    return required
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

/** A body holding only `field`, loaded (trimmed), or `fieldErrors` and any unknown field. */
function loadOnlyText(
  body: Record<string, unknown>,
  field: string,
  fieldErrors: string[] | undefined,
): { text: string } | { errors: FieldErrors } {
  const errors = unknownFieldErrors(body, [field])
  if (fieldErrors !== undefined) {
    errors[field] = fieldErrors
  }
  const value = body[field]
  // The typeof only tells TypeScript what textErrors already checked.
  if (Object.keys(errors).length > 0 || typeof value !== 'string') {
    return { errors }
  }
  return { text: value.trim() }
}

/**
 * A body holding one required text field and nothing else, loaded (trimmed), or what it is
 * refused for: a question's `message` or an answer's `response`. The backend also takes
 * amendments with an answer (ADR-0029), which the web app never sends, so the mock calls any
 * other field unknown (ADR-0060).
 */
export function loadText(
  body: Record<string, unknown>,
  field: string,
): { text: string } | { errors: FieldErrors } {
  return loadOnlyText(body, field, requiredErrors(body, field) ?? textErrors(body[field]))
}

/**
 * A planning rejection's body, its `reason` loaded (trimmed), or what it is refused for
 * (RejectEventSchema, ADR-0093): a missing or null reason gets the schema's own message, a blank
 * or non-text one marshmallow's.
 */
export function loadRejectionReason(
  body: Record<string, unknown>,
): { text: string } | { errors: FieldErrors } {
  const { reason } = body
  const isMissing = reason === undefined || reason === null
  return loadOnlyText(
    body,
    'reason',
    isMissing ? [REJECTION_REASON_REQUIRED_MESSAGE] : textErrors(reason),
  )
}
