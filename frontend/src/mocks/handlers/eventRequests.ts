import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'

import { ROLE } from '@/config/roles'
import type { Role } from '@/config/roles'
import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import type { EventRequestStatus } from '@/config/eventStatus'
import type { Clarification, Decision, EventRequest } from '@/features/eventRequests/api'
import { isRecord } from '@/lib/isRecord'

import type { MockAccount } from '../fixtures/accounts'
import { errorResponse, notAllowed, notAuthenticated, validationError } from '../responses'

import { accountForRequest } from './auth'
import { MOCK_NOW } from './catalogueFixtures'
import {
  DETAIL_FIELDS,
  draftChangeErrors,
  draftErrors,
  submissionErrors,
  withSeconds,
} from './eventRequestRules'
import { PLANNING_EVENT_REQUESTS } from './eventPlanningFixtures'
import { MOCK_EVENT_REQUESTS, NOTHING_RECORDED } from './eventRequestFixtures'
import type { MockEventRequest } from './eventRequestFixtures'
import { loadDecision, loadText } from './eventReviewRules'
import type { LoadedDecision } from './eventReviewRules'

/**
 * Event requests: an organiser's list (SCRUM-7, SCRUM-24, ADR-0020), submitting one
 * (SCRUM-19), saving, changing and submitting a draft (SCRUM-20, ADR-0024), a coordinator's
 * list of the events assigned to them, opening one's record as either (SCRUM-24 AC2, AC9,
 * AC10; ADR-0056), the coordinator starting a review, deciding and asking a question, and an
 * organiser answering it (SCRUM-31, SCRUM-32; ADR-0028, ADR-0029, ADR-0060). Who sees what,
 * the order, and every check are decided here as the backend decides them, never in the UI.
 * A decision, question or answer is made at the mock's "now", MOCK_NOW.
 */

const MY_REQUESTS_PATH = '/api/events/requests'
const DRAFTS_PATH = `${MY_REQUESTS_PATH}/drafts`
const ASSIGNED_PATH = `${MY_REQUESTS_PATH}/assigned`
const NO_ORGANISATION_MESSAGE = 'Your account is not linked to a client organisation yet.'
const NO_REQUESTS_MESSAGE = 'Your organisation has no event requests yet.'
const NO_ASSIGNED_MESSAGE = 'No event requests are assigned to you yet.'
const NOT_FOUND_MESSAGE = 'Event request not found.'
const NOT_A_DRAFT_MESSAGE = 'Only a draft event request can be changed or submitted this way.'
const NOT_AN_OBJECT_MESSAGE = 'Request body must be a JSON object.'
const NOT_REVIEWABLE_MESSAGE = 'Only a submitted event request can be moved to under review.'
const NOT_DECIDABLE_MESSAGE =
  'Only a submitted, under-review, awaiting-clarification, approved or rejected event ' +
  'request can be decided.'
const REASON_REQUIRED_MESSAGE = 'A reason is required to reject a request or to change a decision.'
const DECISION_LOCKED_MESSAGE =
  "The decision can't be changed once the event has an equipment request or a venue " +
  'booking request.'
const CLARIFICATION_OUTSTANDING_MESSAGE =
  "The request can't be approved until the organiser has answered the clarification request."
const CLARIFICATION_NOT_ALLOWED_MESSAGE =
  'Clarification can only be requested while the event request is under review.'
const NOT_AWAITING_CLARIFICATION_MESSAGE =
  'Only an event request awaiting clarification can be answered and resubmitted.'
/** Statuses a request awaits its first decision in (ADR-0028, ADR-0029). */
const AWAITING_DECISION_STATUSES: readonly EventRequestStatus[] = [
  EVENT_REQUEST_STATUS.SUBMITTED,
  EVENT_REQUEST_STATUS.UNDER_REVIEW,
  EVENT_REQUEST_STATUS.AWAITING_CLARIFICATION,
]
/** Statuses a request has been decided in, and may be decided again in, with a reason. */
const DECIDED_STATUSES: readonly EventRequestStatus[] = [
  EVENT_REQUEST_STATUS.APPROVED,
  EVENT_REQUEST_STATUS.REJECTED,
]
const STATUS_BY_OUTCOME: Record<Decision['outcome'], EventRequestStatus> = {
  approved: EVENT_REQUEST_STATUS.APPROVED,
  rejected: EVENT_REQUEST_STATUS.REJECTED,
}
/** Just after the newest fixture, so a request made in the mock lists first, as it would. */
const FIRST_NEW_CREATED_AT = Date.parse('2026-10-08T02:00:00+00:00')

/** The requests as they stand; made, changed and submitted ones included. Reset per test. */
let storedRequests: MockEventRequest[] = []
let madeCount = 0

/** Put the requests back as the fixture has them. Runs after every test. */
export function resetMockEventRequests(): void {
  storedRequests = [...MOCK_EVENT_REQUESTS, ...PLANNING_EVENT_REQUESTS].map((stored) => ({
    ...stored,
    request: { ...stored.request },
  }))
  madeCount = 0
}
resetMockEventRequests()

/** The organisation's requests, and of its drafts only the organiser's own (SCRUM-20 AC4). */
function visibleTo(organiserId: number, organisationId: number) {
  return (stored: MockEventRequest) =>
    stored.organisationId === organisationId &&
    (stored.request.status !== EVENT_REQUEST_STATUS.DRAFT || stored.organiserId === organiserId)
}

/** Newest request first, as the backend lists them. */
function newestFirst(a: MockEventRequest, b: MockEventRequest): number {
  return (b.request.created_at ?? '').localeCompare(a.request.created_at ?? '')
}

/** The caller, if they hold one of `roles`; otherwise the refusal, as the decorators give it. */
function callerOrRefusal(request: Request, roles: readonly Role[]) {
  const account = accountForRequest(request)
  if (account === undefined) {
    return { refusal: notAuthenticated() }
  }
  if (!roles.includes(account.role)) {
    return { refusal: notAllowed() }
  }
  return { caller: account }
}

/** The caller, if they may work on their organisation's requests; otherwise the refusal. */
function organiserOrRefusal(request: Request) {
  const found = callerOrRefusal(request, [ROLE.EVENT_ORGANISER])
  if ('refusal' in found) {
    return { refusal: found.refusal }
  }
  const account = found.caller
  if (account.organisation_id === null) {
    return {
      refusal: errorResponse(403, 'organiser_without_organisation', NO_ORGANISATION_MESSAGE),
    }
  }
  return { organiser: account, organisationId: account.organisation_id }
}

async function bodyOf(request: Request): Promise<Record<string, unknown>> {
  const body: unknown = await request.json().catch(() => null)
  return isRecord(body) ? body : {}
}

/** The details the backend stores: what was sent, trimmed, with times in its own format. */
function detailsFrom(body: Record<string, unknown>): Partial<EventRequest> {
  const details: Record<string, unknown> = {}
  for (const name of DETAIL_FIELDS) {
    if (!(name in body)) {
      continue
    }
    const value = body[name]
    if (typeof value === 'string' && (name === 'start_time' || name === 'end_time')) {
      details[name] = withSeconds(value)
    } else if (typeof value === 'string') {
      details[name] = value.trim() === '' && name !== 'name' ? null : value.trim()
    } else {
      details[name] = value
    }
  }
  return details
}

/** A new request, filed under the organiser's organisation with the next mock reference. */
function make(organiser: MockAccount, organisationId: number, details: Partial<EventRequest>) {
  madeCount += 1
  const request: EventRequest = {
    reference: `EVR-NEW${String(madeCount).padStart(5, '0')}`,
    status: EVENT_REQUEST_STATUS.DRAFT,
    name: '',
    purpose: null,
    description: null,
    proposed_date: null,
    end_date: null,
    start_time: null,
    end_time: null,
    expected_attendance: null,
    venue_requirements: null,
    accessibility_needs: null,
    equipment_requirements: null,
    registration_required: false,
    created_at: new Date(FIRST_NEW_CREATED_AT + madeCount * 60_000).toISOString(),
    ...details,
  }
  storedRequests.push({
    organiserId: organiser.id,
    organisationId,
    coordinator: null,
    request,
    record: NOTHING_RECORDED,
  })
  return request
}

/** Submitted, ending the day it starts unless it said otherwise (ADR-0002). */
function markSubmitted(request: EventRequest): void {
  request.status = EVENT_REQUEST_STATUS.SUBMITTED
  request.end_date = request.end_date ?? request.proposed_date
}

/** The details a draft has, leaving out the empty ones, as the backend checks a draft it submits. */
function savedDetails(request: EventRequest): Record<string, unknown> {
  const details: Record<string, unknown> = {}
  for (const name of DETAIL_FIELDS) {
    if (request[name] !== null) {
      details[name] = request[name]
    }
  }
  return details
}

/** One of the organisation's requests the organiser may see (SCRUM-7, SCRUM-20 AC4). */
function visibleRequest(organiserId: number, organisationId: number, reference: unknown) {
  return storedRequests
    .filter(visibleTo(organiserId, organisationId))
    .find((stored) => stored.request.reference === reference)
}

/**
 * One of the organiser's own drafts, or the backend's refusal: not found when it isn't in
 * their organisation or is a colleague's draft, and not a draft once it has been submitted.
 */
function ownDraftOrRefusal(organiser: MockAccount, organisationId: number, reference: unknown) {
  const stored = visibleRequest(organiser.id, organisationId, reference)
  if (stored === undefined) {
    return { refusal: errorResponse(404, 'not_found', NOT_FOUND_MESSAGE) }
  }
  if (stored.request.status !== EVENT_REQUEST_STATUS.DRAFT) {
    return { refusal: errorResponse(409, 'request_not_draft', NOT_A_DRAFT_MESSAGE) }
  }
  return { draft: stored.request }
}

/** A request's record as the backend shows it: the coordinator by name and email, no ids. */
function recordOf(stored: MockEventRequest) {
  const { coordinator } = stored
  const contact =
    coordinator === null ? null : { full_name: coordinator.full_name, email: coordinator.email }
  return { ...stored.request, ...stored.record, coordinator: contact, equipment_lines: [] }
}

/** One of the coordinator's own assigned requests; no other, by any link (SCRUM-24 AC10). */
function assignedRequest(coordinatorId: number, reference: unknown) {
  return storedRequests.find(
    (stored) => stored.request.reference === reference && stored.coordinator?.id === coordinatorId,
  )
}

/**
 * The calling coordinator and their own assigned request, or the refusal: anyone but a
 * coordinator is refused by role, and another's request is "not found" (SCRUM-31 AC5).
 */
export function assignedOrRefusal(request: Request, reference: unknown) {
  const found = callerOrRefusal(request, [ROLE.EVENT_COORDINATOR])
  if ('refusal' in found) {
    return { refusal: found.refusal }
  }
  const stored = assignedRequest(found.caller.id, reference)
  if (stored === undefined) {
    return { refusal: errorResponse(404, 'not_found', NOT_FOUND_MESSAGE) }
  }
  return { coordinator: found.caller, stored }
}

/** The body, if it is a JSON object; anything else is refused before its fields are read. */
async function objectBodyOrRefusal(request: Request) {
  const body: unknown = await request.json().catch(() => null)
  if (!isRecord(body)) {
    return { refusal: errorResponse(400, 'validation_error', NOT_AN_OBJECT_MESSAGE) }
  }
  return { body }
}

/**
 * Whether a decision may be made in the request's state: not once the event is past its
 * decision, and not a new one once it has an equipment request (SCRUM-31 AC7, ADR-0028).
 */
function undecidableRefusal(stored: MockEventRequest) {
  const { status } = stored.request
  const isDecided = DECIDED_STATUSES.includes(status)
  if (!isDecided && !AWAITING_DECISION_STATUSES.includes(status)) {
    return errorResponse(409, 'request_not_decidable', NOT_DECIDABLE_MESSAGE)
  }
  if (isDecided && stored.hasEquipmentRequest === true) {
    return errorResponse(409, 'decision_locked', DECISION_LOCKED_MESSAGE)
  }
  return null
}

/**
 * Whether the decision is refused for what it says: a rejection or a change of decision with no
 * reason (SCRUM-31 AC4, AC6), or an approval while a question is outstanding (SCRUM-32 AC3).
 */
function decisionRefusal(status: EventRequestStatus, decision: LoadedDecision) {
  const needsReason = decision.outcome === 'rejected' || DECIDED_STATUSES.includes(status)
  if (decision.reason === null && needsReason) {
    return validationError({ reason: [REASON_REQUIRED_MESSAGE] })
  }
  if (decision.outcome === 'approved' && status === EVENT_REQUEST_STATUS.AWAITING_CLARIFICATION) {
    return errorResponse(409, 'clarification_outstanding', CLARIFICATION_OUTSTANDING_MESSAGE)
  }
  return null
}

/** The exchange with its last question answered: an answer belongs to the question before it. */
function withLastAnswered(clarifications: Clarification[], answer: Partial<Clarification>) {
  const lastIndex = clarifications.length - 1
  return clarifications.map((exchange, index) =>
    index === lastIndex ? { ...exchange, ...answer } : exchange,
  )
}

export const eventRequestHandlers: RequestHandler[] = [
  http.get(MY_REQUESTS_PATH, ({ request }) => {
    const caller = organiserOrRefusal(request)
    if ('refusal' in caller) {
      return caller.refusal
    }

    const visible = storedRequests.filter(visibleTo(caller.organiser.id, caller.organisationId))
    const listed = [...visible].sort(newestFirst).map((stored) => stored.request)
    if (listed.length === 0) {
      return HttpResponse.json({ event_requests: [], message: NO_REQUESTS_MESSAGE })
    }
    return HttpResponse.json({ event_requests: listed })
  }),

  http.post(MY_REQUESTS_PATH, async ({ request }) => {
    const caller = organiserOrRefusal(request)
    if ('refusal' in caller) {
      return caller.refusal
    }
    const body = await bodyOf(request)
    const errors = submissionErrors(body)
    if (Object.keys(errors).length > 0) {
      return validationError(errors)
    }

    const made = make(caller.organiser, caller.organisationId, detailsFrom(body))
    markSubmitted(made)
    return HttpResponse.json(made, { status: 201 })
  }),

  http.post(DRAFTS_PATH, async ({ request }) => {
    const caller = organiserOrRefusal(request)
    if ('refusal' in caller) {
      return caller.refusal
    }
    const body = await bodyOf(request)
    const errors = draftErrors(body)
    if (Object.keys(errors).length > 0) {
      return validationError(errors)
    }

    const made = make(caller.organiser, caller.organisationId, detailsFrom(body))
    return HttpResponse.json(made, { status: 201 })
  }),

  http.patch(`${DRAFTS_PATH}/:reference`, async ({ request, params }) => {
    const caller = organiserOrRefusal(request)
    if ('refusal' in caller) {
      return caller.refusal
    }
    const found = ownDraftOrRefusal(caller.organiser, caller.organisationId, params.reference)
    if ('refusal' in found) {
      return found.refusal
    }
    const body = await bodyOf(request)
    const errors = draftChangeErrors(body)
    if (Object.keys(errors).length > 0) {
      return validationError(errors)
    }

    Object.assign(found.draft, detailsFrom(body))
    return HttpResponse.json(found.draft)
  }),

  http.post(`${DRAFTS_PATH}/:reference/submit`, ({ request, params }) => {
    const caller = organiserOrRefusal(request)
    if ('refusal' in caller) {
      return caller.refusal
    }
    const found = ownDraftOrRefusal(caller.organiser, caller.organisationId, params.reference)
    if ('refusal' in found) {
      return found.refusal
    }
    const errors = submissionErrors(savedDetails(found.draft))
    if (Object.keys(errors).length > 0) {
      return validationError(errors)
    }

    markSubmitted(found.draft)
    return HttpResponse.json(found.draft)
  }),

  http.get(ASSIGNED_PATH, ({ request }) => {
    const found = callerOrRefusal(request, [ROLE.EVENT_COORDINATOR])
    if ('refusal' in found) {
      return found.refusal
    }

    const assigned = storedRequests.filter((stored) => stored.coordinator?.id === found.caller.id)
    const listed = [...assigned].sort(newestFirst).map((stored) => stored.request)
    if (listed.length === 0) {
      return HttpResponse.json({ event_requests: [], message: NO_ASSIGNED_MESSAGE })
    }
    return HttpResponse.json({ event_requests: listed })
  }),

  http.get(`${MY_REQUESTS_PATH}/:reference`, ({ request, params }) => {
    // The backend matches a fixed path such as /unassigned before a reference, so the mock
    // lets anything that isn't a reference through to that path's own handler.
    if (typeof params.reference !== 'string' || !params.reference.startsWith('EVR-')) {
      return undefined
    }
    const found = callerOrRefusal(request, [ROLE.EVENT_ORGANISER, ROLE.EVENT_COORDINATOR])
    if ('refusal' in found) {
      return found.refusal
    }

    // Anything they may not open is "not found", so nobody learns it exists (ADR-0012).
    let stored: MockEventRequest | undefined
    if (found.caller.role === ROLE.EVENT_COORDINATOR) {
      stored = assignedRequest(found.caller.id, params.reference)
    } else {
      const organiser = organiserOrRefusal(request)
      if ('refusal' in organiser) {
        return organiser.refusal
      }
      stored = visibleRequest(organiser.organiser.id, organiser.organisationId, params.reference)
    }
    if (stored === undefined) {
      return errorResponse(404, 'not_found', NOT_FOUND_MESSAGE)
    }
    return HttpResponse.json(recordOf(stored))
  }),

  http.post(`${MY_REQUESTS_PATH}/:reference/review`, ({ request, params }) => {
    const found = assignedOrRefusal(request, params.reference)
    if ('refusal' in found) {
      return found.refusal
    }
    const reviewed = found.stored.request
    if (reviewed.status !== EVENT_REQUEST_STATUS.SUBMITTED) {
      return errorResponse(409, 'request_not_reviewable', NOT_REVIEWABLE_MESSAGE)
    }

    reviewed.status = EVENT_REQUEST_STATUS.UNDER_REVIEW
    return HttpResponse.json(reviewed)
  }),

  http.post(`${MY_REQUESTS_PATH}/:reference/decide`, async ({ request, params }) => {
    const found = assignedOrRefusal(request, params.reference)
    if ('refusal' in found) {
      return found.refusal
    }
    const { coordinator, stored } = found
    const undecidable = undecidableRefusal(stored)
    if (undecidable !== null) {
      return undecidable
    }
    const payload = await objectBodyOrRefusal(request)
    if ('refusal' in payload) {
      return payload.refusal
    }
    const loaded = loadDecision(payload.body)
    if ('errors' in loaded) {
      return validationError(loaded.errors)
    }
    const { decision } = loaded
    const refused = decisionRefusal(stored.request.status, decision)
    if (refused !== null) {
      return refused
    }

    stored.request.status = STATUS_BY_OUTCOME[decision.outcome]
    stored.record = {
      ...stored.record,
      decision: { ...decision, decided_by: coordinator.full_name, decided_at: MOCK_NOW },
    }
    return HttpResponse.json(stored.request)
  }),

  http.post(`${MY_REQUESTS_PATH}/:reference/request-clarification`, async ({ request, params }) => {
    const found = assignedOrRefusal(request, params.reference)
    if ('refusal' in found) {
      return found.refusal
    }
    const { coordinator, stored } = found
    if (stored.request.status !== EVENT_REQUEST_STATUS.UNDER_REVIEW) {
      return errorResponse(409, 'clarification_not_allowed', CLARIFICATION_NOT_ALLOWED_MESSAGE)
    }
    const payload = await objectBodyOrRefusal(request)
    if ('refusal' in payload) {
      return payload.refusal
    }
    const loaded = loadText(payload.body, 'message')
    if ('errors' in loaded) {
      return validationError(loaded.errors)
    }

    stored.request.status = EVENT_REQUEST_STATUS.AWAITING_CLARIFICATION
    const question: Clarification = {
      message: loaded.text,
      requested_by: coordinator.full_name,
      requested_at: MOCK_NOW,
      response: null,
      answered_by: null,
      answered_at: null,
    }
    stored.record = {
      ...stored.record,
      clarifications: [...stored.record.clarifications, question],
    }
    return HttpResponse.json(stored.request)
  }),

  http.post(`${MY_REQUESTS_PATH}/:reference/resubmit`, async ({ request, params }) => {
    const caller = organiserOrRefusal(request)
    if ('refusal' in caller) {
      return caller.refusal
    }
    const { organiser, organisationId } = caller
    const stored = visibleRequest(organiser.id, organisationId, params.reference)
    if (stored === undefined) {
      return errorResponse(404, 'not_found', NOT_FOUND_MESSAGE)
    }
    if (stored.request.status !== EVENT_REQUEST_STATUS.AWAITING_CLARIFICATION) {
      return errorResponse(
        409,
        'request_not_awaiting_clarification',
        NOT_AWAITING_CLARIFICATION_MESSAGE,
      )
    }
    const payload = await objectBodyOrRefusal(request)
    if ('refusal' in payload) {
      return payload.refusal
    }
    const loaded = loadText(payload.body, 'response')
    if ('errors' in loaded) {
      return validationError(loaded.errors)
    }

    stored.request.status = EVENT_REQUEST_STATUS.UNDER_REVIEW
    const answer = {
      response: loaded.text,
      answered_by: organiser.full_name,
      answered_at: MOCK_NOW,
    }
    stored.record = {
      ...stored.record,
      clarifications: withLastAnswered(stored.record.clarifications, answer),
    }
    return HttpResponse.json(stored.request)
  }),
]
