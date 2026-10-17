import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'

import { ROLE } from '@/config/roles'
import { CHECKLIST, SAFETY_OUTCOME } from '@/features/safety/constants'
import type { SafetyOutcome } from '@/features/safety/constants'
import type { FieldErrors } from '@/lib/api'
import { isRecord } from '@/lib/isRecord'

import { errorResponse, notAllowed, notAuthenticated, validationError } from '../responses'

import { accountForRequest } from './auth'
import { MOCK_SAFETY_EVENTS } from './safetyFixtures'
import type { MockSafetyEvent } from './safetyFixtures'

/**
 * The Safety Officer's endpoints (SCRUM-97 list, SCRUM-98 outcome), answering as
 * backend/app/modules/events/routes.py and services.py do, error bodies and messages included.
 * Only a Safety Officer may use them; one list serves every Safety Officer (ADR-0047).
 */

export const NO_EVENTS_MESSAGE = 'No events are waiting for a safety review.'
export const REASON_REQUIRED_MESSAGE =
  'A reason is required to reject the event or request changes.'
export const NOT_IN_SAFETY_REVIEW_MESSAGE =
  'Only an event in Safety Review can get a safety outcome.'
export const ALREADY_APPROVED_MESSAGE = 'The Safety Officer has already approved this event.'
const NOT_FOUND_MESSAGE = 'Event request not found.'
const NOT_AN_OBJECT_MESSAGE = 'Request body must be a JSON object.'
const MISSING_MESSAGE = 'Missing data for required field.'
const NULL_MESSAGE = 'Field may not be null.'
const BLANK_MESSAGE = 'Must not be blank.'
const NOT_TEXT_MESSAGE = 'Not a valid string.'
const UNKNOWN_OUTCOME_MESSAGE = 'Outcome must be approved, rejected or changes_requested.'
const NOT_AN_OBJECT_FIELD_MESSAGE = 'Invalid input type.'

const OUTCOMES: readonly unknown[] = Object.values(SAFETY_OUTCOME)

let events: MockSafetyEvent[] = []

/** Put every event back as it started, so no test sees another test's outcome. */
export function resetMockSafety(): void {
  events = MOCK_SAFETY_EVENTS.map((mock) => ({ ...mock, event: { ...mock.event } }))
}
resetMockSafety()

/** The 401 or 403 the backend's decorators send, or null when the caller is a Safety Officer. */
function refusalFor(request: Request) {
  const account = accountForRequest(request)
  if (account === undefined) {
    return notAuthenticated()
  }
  if (account.role !== ROLE.SAFETY_OFFICER) {
    return notAllowed()
  }
  return null
}

/** The backend's list: in Safety Review and not yet approved, by date, then start time. */
function awaitingReview(): MockSafetyEvent[] {
  const awaiting = events.filter(
    (mock) => mock.event.status === 'safety_review' && !mock.safety_approved,
  )
  return awaiting.sort(
    (left, right) =>
      left.event.proposed_date.localeCompare(right.event.proposed_date) ||
      left.event.start_time.localeCompare(right.event.start_time),
  )
}

/** The listed shape: the event, its venues and equipment, without the mock's own flag. */
function asListed({ event, venues, equipment }: MockSafetyEvent) {
  return { event, venues, equipment }
}

/** marshmallow's message for a required text field, or null when `value` is fine. */
function textFieldError(value: unknown): string | null {
  if (value === undefined) {
    return MISSING_MESSAGE
  }
  if (value === null) {
    return NULL_MESSAGE
  }
  if (typeof value !== 'string') {
    return NOT_TEXT_MESSAGE
  }
  return value.trim() === '' ? BLANK_MESSAGE : null
}

/** The checklist's messages, as SafetyChecklistSchema gives them, or null when it is fine. */
function checklistErrors(checklist: unknown): string[] | FieldErrors | null {
  if (checklist === undefined) {
    return [MISSING_MESSAGE]
  }
  if (!isRecord(checklist)) {
    return { _schema: [NOT_AN_OBJECT_FIELD_MESSAGE] }
  }
  const errors: FieldErrors = {}
  for (const { item } of CHECKLIST) {
    const error = textFieldError(checklist[item])
    if (error !== null) {
      errors[item] = [error]
    }
  }
  return Object.keys(errors).length > 0 ? errors : null
}

function outcomeError(outcome: unknown): string | null {
  if (outcome === undefined) {
    return MISSING_MESSAGE
  }
  if (outcome === null) {
    return NULL_MESSAGE
  }
  return OUTCOMES.includes(outcome) ? null : UNKNOWN_OUTCOME_MESSAGE
}

/** A reason may be left out or null; one that is sent must be text that isn't blank. */
function reasonError(reason: unknown): string | null {
  if (reason === undefined || reason === null) {
    return null
  }
  return textFieldError(reason)
}

/**
 * RecordSafetyOutcomeSchema's answer to the body: every field's messages, and only when the
 * fields are all valid, the reason a Reject or Request Changes needs.
 */
function bodyErrors(body: Record<string, unknown>): Record<string, string[] | FieldErrors> {
  const errors: Record<string, string[] | FieldErrors> = {}
  const outcome = outcomeError(body.outcome)
  if (outcome !== null) {
    errors.outcome = [outcome]
  }
  const checklist = checklistErrors(body.checklist)
  if (checklist !== null) {
    errors.checklist = checklist
  }
  const reason = reasonError(body.reason)
  if (reason !== null) {
    errors.reason = [reason]
  }
  const fieldsAreValid = Object.keys(errors).length === 0
  const needsReason = body.outcome !== SAFETY_OUTCOME.APPROVED
  if (fieldsAreValid && needsReason && (body.reason === undefined || body.reason === null)) {
    errors.reason = [REASON_REQUIRED_MESSAGE]
  }
  return errors
}

export const safetyHandlers: RequestHandler[] = [
  http.get('/api/events/requests/awaiting-safety-review', ({ request }) => {
    const refusal = refusalFor(request)
    if (refusal !== null) {
      return refusal
    }
    const awaiting = awaitingReview().map(asListed)
    if (awaiting.length === 0) {
      return HttpResponse.json({ events: [], message: NO_EVENTS_MESSAGE })
    }
    return HttpResponse.json({ events: awaiting })
  }),

  http.post('/api/events/requests/:reference/safety-outcome', async ({ request, params }) => {
    const refusal = refusalFor(request)
    if (refusal !== null) {
      return refusal
    }
    // The backend's order: the body first, then the event, then whether it may get an outcome.
    const body: unknown = await request.json().catch(() => null)
    if (!isRecord(body)) {
      return errorResponse(400, 'validation_error', NOT_AN_OBJECT_MESSAGE)
    }
    const errors = bodyErrors(body)
    if (Object.keys(errors).length > 0) {
      return validationError(errors)
    }
    const found = events.find((mock) => mock.event.reference === params.reference)
    if (found === undefined) {
      return errorResponse(404, 'not_found', NOT_FOUND_MESSAGE)
    }
    if (found.event.status !== 'safety_review') {
      return errorResponse(409, 'safety_outcome_not_allowed', NOT_IN_SAFETY_REVIEW_MESSAGE)
    }
    if (found.safety_approved) {
      return errorResponse(409, 'safety_outcome_not_allowed', ALREADY_APPROVED_MESSAGE)
    }

    const outcome = body.outcome as SafetyOutcome // checked against the outcomes above
    const approved = outcome === SAFETY_OUTCOME.APPROVED
    found.safety_approved = approved
    found.event.status = approved ? 'safety_review' : 'approved'
    // Reduced on purpose: the real route sends the whole EventRequestSchema dump, which
    // src/integration/safety.int.test.ts pins. The web app reads only these event fields.
    return HttpResponse.json(found.event)
  }),
]
