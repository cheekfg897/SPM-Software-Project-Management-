import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'

import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import type { EventRequestStatus } from '@/config/eventStatus'
import type { RequestedChange } from '@/features/eventRequests/api'
import type { FieldErrors } from '@/lib/api'

import type { MockAccount } from '../fixtures/accounts'
import { errorResponse, validationError } from '../responses'

import { MOCK_NOW } from './catalogueFixtures'
import { addChangeRequest, changeRequestsOf, replaceChangeRequest } from './changeRequestStore'
import { currentValue, fieldErrors, loadedValues, windowErrors, withEndDate } from './eventEdits'
import type { EditableField, Values } from './eventEdits'
import type { MockEventRequest } from './eventRequestFixtures'
import { objectBodyOrRefusal, organiserOrRefusal, visibleRequest } from './eventRequests'

/**
 * An organiser's change request (SCRUM-56, ADR-0126): raising one on their own submitted event
 * (POST /api/events/requests/<reference>/change-requests) and withdrawing a Pending one
 * (POST .../change-requests/<id>/withdraw). The request keeps each value asked for beside the
 * event's value when raised, and the event itself is left as it is (AC3). Checks run in the
 * backend's order: the organisation and reference (404), the owner (403), the status (409), the
 * body (400, each value checked as the coordinator's edit checks it), something to change (400),
 * then one Pending request per event (409). The coordinator's notice isn't raised: the
 * notifications mock serves only its seeded notices. A request is raised or withdrawn at the
 * mock's "now", MOCK_NOW.
 */

const REQUESTS_PATH = '/api/events/requests'
const CHANGE_REQUESTS_PATH = `${REQUESTS_PATH}/:reference/change-requests`
const NOT_FOUND_MESSAGE = 'Event request not found.'
const NOT_THE_ORGANISER_MESSAGE =
  'Only the organiser who submitted this event can request a change to it or withdraw one.'
const REASON_REQUIRED_MESSAGE = 'Say why the change is needed.'
const NOTHING_TO_CHANGE_MESSAGE =
  "Say what should change: give at least one of the event's details a new value."
const ALREADY_PENDING_MESSAGE =
  'A change request is already waiting for the coordinator. Withdraw it, or wait for their ' +
  'decision, before raising another.'
const CHANGE_REQUEST_NOT_FOUND_MESSAGE = 'Change request not found.'
/** Every status from Submitted to Confirmed (`CHANGE_REQUESTABLE_STATUSES`, AC1). */
const REQUESTABLE_STATUSES: readonly EventRequestStatus[] = [
  EVENT_REQUEST_STATUS.SUBMITTED,
  EVENT_REQUEST_STATUS.UNDER_REVIEW,
  EVENT_REQUEST_STATUS.AWAITING_CLARIFICATION,
  EVENT_REQUEST_STATUS.APPROVED,
  EVENT_REQUEST_STATUS.SAFETY_REVIEW,
  EVENT_REQUEST_STATUS.CONFIRMED,
]
/** What a change request can ask for, in the backend's order (`REQUESTABLE_FIELDS`, AC2). */
const REQUESTABLE_FIELDS: readonly EditableField[] = [
  'proposed_date',
  'end_date',
  'start_time',
  'end_time',
  'expected_attendance',
  'venue_requirements',
  'equipment_requirements',
  'programme_notes',
]

function isRequestable(name: string): boolean {
  return (REQUESTABLE_FIELDS as readonly string[]).includes(name)
}

/** The fields of `body` a change request can ask for. */
function requestableOf(body: Record<string, unknown>): Record<string, unknown> {
  const requestable: Record<string, unknown> = {}
  for (const [name, value] of Object.entries(body)) {
    if (isRequestable(name)) {
      requestable[name] = value
    }
  }
  return requestable
}

/** Why the body is refused, field by field: an unknown field, why, then each value's own rules. */
function bodyErrors(body: Record<string, unknown>): FieldErrors {
  const errors: FieldErrors = {}
  for (const name of Object.keys(body)) {
    if (name !== 'reason' && !isRequestable(name)) {
      errors[name] = ['Unknown field.']
    }
  }
  const { reason } = body
  if (typeof reason !== 'string' || reason.trim() === '') {
    errors.reason = [REASON_REQUIRED_MESSAGE]
  }
  return { ...errors, ...fieldErrors(requestableOf(body)) }
}

/** Each loaded value that differs from what the event holds, beside what it holds now. */
function changesTo(stored: MockEventRequest, values: Values): RequestedChange[] {
  const changes: RequestedChange[] = []
  for (const [name, value] of Object.entries(values)) {
    const field = name as EditableField // Only requestable fields were loaded.
    const previous = currentValue(stored, field)
    const requested = value ?? null
    if (previous !== requested) {
      changes.push({ field, previous_value: previous, requested_value: requested })
    }
  }
  return changes
}

/**
 * The caller and their own event, or the refusal: another organisation's event, or one they can't
 * see, is "not found" (ADR-0012), and a colleague's is not theirs (AC6).
 */
function ownEventOrRefusal(request: Request, reference: unknown) {
  const caller = organiserOrRefusal(request)
  if ('refusal' in caller) {
    return { refusal: caller.refusal }
  }
  const { organiser, organisationId } = caller
  const stored = visibleRequest(organiser.id, organisationId, reference)
  if (stored === undefined) {
    return { refusal: errorResponse(404, 'not_found', NOT_FOUND_MESSAGE) }
  }
  if (stored.organiserId !== organiser.id) {
    return { refusal: errorResponse(403, 'not_event_organiser', NOT_THE_ORGANISER_MESSAGE) }
  }
  return { organiser, stored }
}

/** The new request, or why it is refused; the event's status is already checked. */
function raised(stored: MockEventRequest, organiser: MockAccount, body: Record<string, unknown>) {
  const errors = bodyErrors(body)
  if (Object.keys(errors).length > 0) {
    return validationError(errors)
  }
  const values = withEndDate(loadedValues(body, REQUESTABLE_FIELDS), stored.request)
  const refused = windowErrors(values, stored.request)
  if (refused !== null) {
    return validationError(refused)
  }
  const changes = changesTo(stored, values)
  if (changes.length === 0) {
    return errorResponse(400, 'validation_error', NOTHING_TO_CHANGE_MESSAGE)
  }
  const { reference } = stored.request
  const isPending = changeRequestsOf(reference).some((each) => each.status === 'pending')
  if (isPending) {
    return errorResponse(409, 'conflict', ALREADY_PENDING_MESSAGE)
  }

  const kept = addChangeRequest(reference, {
    status: 'pending',
    changes,
    reason: String(body.reason).trim(),
    raised_by: organiser.full_name,
    raised_at: MOCK_NOW,
    withdrawn_at: null,
    withdrawal_note: null,
  })
  return HttpResponse.json(kept, { status: 201 })
}

export const changeRequestHandlers: RequestHandler[] = [
  http.post(CHANGE_REQUESTS_PATH, async ({ request, params }) => {
    const found = ownEventOrRefusal(request, params.reference)
    if ('refusal' in found) {
      return found.refusal
    }
    const { organiser, stored } = found
    const { status } = stored.request
    if (!REQUESTABLE_STATUSES.includes(status)) {
      const message = `A change can't be requested for a ${status} event.`
      return errorResponse(409, 'change_request_not_allowed', message)
    }
    const payload = await objectBodyOrRefusal(request)
    if ('refusal' in payload) {
      return payload.refusal
    }
    return raised(stored, organiser, payload.body)
  }),

  http.post(`${CHANGE_REQUESTS_PATH}/:id/withdraw`, ({ request, params }) => {
    const found = ownEventOrRefusal(request, params.reference)
    if ('refusal' in found) {
      return found.refusal
    }
    const { reference } = found.stored.request
    const changeRequest = changeRequestsOf(reference).find((each) => String(each.id) === params.id)
    if (changeRequest === undefined) {
      return errorResponse(404, 'not_found', CHANGE_REQUEST_NOT_FOUND_MESSAGE)
    }
    if (changeRequest.status !== 'pending') {
      const message = `Only a pending change request can be withdrawn; this one is ${changeRequest.status}.`
      return errorResponse(409, 'change_request_not_pending', message)
    }

    const withdrawn = { ...changeRequest, status: 'withdrawn' as const, withdrawn_at: MOCK_NOW }
    replaceChangeRequest(reference, withdrawn)
    return HttpResponse.json(withdrawn)
  }),
]
