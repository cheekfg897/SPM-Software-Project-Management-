import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'

import { ROLE } from '@/config/roles'
import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import type { EventRequest } from '@/features/eventRequests/api'
import { isRecord } from '@/lib/isRecord'

import type { MockAccount } from '../fixtures/accounts'
import {
  errorResponse,
  INVALID_TOKEN_MESSAGE,
  NOT_PERMITTED_MESSAGE,
  validationError,
} from '../responses'

import { accountForRequest } from './auth'
import {
  DETAIL_FIELDS,
  draftChangeErrors,
  draftErrors,
  submissionErrors,
  withSeconds,
} from './eventRequestRules'
import { MOCK_EVENT_REQUESTS } from './eventRequestFixtures'
import type { MockEventRequest } from './eventRequestFixtures'

/**
 * An Event Organiser's event requests: the list (SCRUM-7, SCRUM-24, ADR-0020), submitting one
 * (SCRUM-19), saving, changing and submitting a draft (SCRUM-20, ADR-0024), and opening one.
 * Who sees what, the order, and every check are decided here as the backend decides them,
 * never in the UI.
 */

const MY_REQUESTS_PATH = '/api/events/requests'
const DRAFTS_PATH = `${MY_REQUESTS_PATH}/drafts`
const NO_ORGANISATION_MESSAGE = 'Your account is not linked to a client organisation yet.'
const NO_REQUESTS_MESSAGE = 'Your organisation has no event requests yet.'
const NOT_FOUND_MESSAGE = 'Event request not found.'
const NOT_A_DRAFT_MESSAGE = 'Only a draft event request can be changed or submitted this way.'
/** Just after the newest fixture, so a request made in the mock lists first, as it would. */
const FIRST_NEW_CREATED_AT = Date.parse('2026-10-08T02:00:00+00:00')

/** The requests as they stand; made, changed and submitted ones included. Reset per test. */
let storedRequests: MockEventRequest[] = []
let madeCount = 0

/** Put the requests back as the fixture has them. Runs after every test. */
export function resetMockEventRequests(): void {
  storedRequests = MOCK_EVENT_REQUESTS.map((stored) => ({
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

/** The caller, if they may work on their organisation's requests; otherwise the refusal. */
function organiserOrRefusal(request: Request) {
  const account = accountForRequest(request)
  if (account === undefined) {
    return { refusal: errorResponse(401, 'authentication_error', INVALID_TOKEN_MESSAGE) }
  }
  if (account.role !== ROLE.EVENT_ORGANISER) {
    return { refusal: errorResponse(403, 'authorization_error', NOT_PERMITTED_MESSAGE) }
  }
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
  storedRequests.push({ organiserId: organiser.id, organisationId, request })
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

/**
 * One of the organiser's own drafts, or the backend's refusal: not found when it isn't in
 * their organisation or is a colleague's draft, and not a draft once it has been submitted.
 */
function ownDraftOrRefusal(organiser: MockAccount, organisationId: number, reference: unknown) {
  const stored = storedRequests
    .filter(visibleTo(organiser.id, organisationId))
    .find((candidate) => candidate.request.reference === reference)
  if (stored === undefined) {
    return { refusal: errorResponse(404, 'not_found', NOT_FOUND_MESSAGE) }
  }
  if (stored.request.status !== EVENT_REQUEST_STATUS.DRAFT) {
    return { refusal: errorResponse(409, 'request_not_draft', NOT_A_DRAFT_MESSAGE) }
  }
  return { draft: stored.request }
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

  http.get(`${MY_REQUESTS_PATH}/:reference`, ({ request, params }) => {
    // The backend matches a fixed path such as /unassigned before a reference, so the mock
    // lets anything that isn't a reference through to that path's own handler.
    if (typeof params.reference !== 'string' || !params.reference.startsWith('EVR-')) {
      return undefined
    }
    const caller = organiserOrRefusal(request)
    if ('refusal' in caller) {
      return caller.refusal
    }

    const stored = storedRequests
      .filter(visibleTo(caller.organiser.id, caller.organisationId))
      .find((candidate) => candidate.request.reference === params.reference)
    if (stored === undefined) {
      return errorResponse(404, 'not_found', NOT_FOUND_MESSAGE)
    }
    return HttpResponse.json(stored.request)
  }),
]
