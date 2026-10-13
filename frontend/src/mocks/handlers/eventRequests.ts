import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'

import { ROLE } from '@/config/roles'
import { EVENT_REQUEST_STATUS } from '@/features/eventRequests/constants'

import { errorResponse, INVALID_TOKEN_MESSAGE, NOT_PERMITTED_MESSAGE } from '../responses'

import { accountForRequest } from './auth'
import { MOCK_EVENT_REQUESTS } from './eventRequestFixtures'
import type { MockEventRequest } from './eventRequestFixtures'

/**
 * The organiser's event list, GET /api/events/requests (SCRUM-7, SCRUM-24, ADR-0020). Who sees
 * what, and in what order, is decided here as the backend decides it, never in the UI.
 */

const MY_REQUESTS_PATH = '/api/events/requests'
const NO_ORGANISATION_MESSAGE = 'Your account is not linked to a client organisation yet.'
const NO_REQUESTS_MESSAGE = 'Your organisation has no event requests yet.'

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

export const eventRequestHandlers: RequestHandler[] = [
  http.get(MY_REQUESTS_PATH, ({ request }) => {
    const account = accountForRequest(request)
    if (account === undefined) {
      return errorResponse(401, 'authentication_error', INVALID_TOKEN_MESSAGE)
    }
    if (account.role !== ROLE.EVENT_ORGANISER) {
      return errorResponse(403, 'authorization_error', NOT_PERMITTED_MESSAGE)
    }
    if (account.organisation_id === null) {
      return errorResponse(403, 'organiser_without_organisation', NO_ORGANISATION_MESSAGE)
    }

    const visible = MOCK_EVENT_REQUESTS.filter(visibleTo(account.id, account.organisation_id))
    const listed = [...visible].sort(newestFirst).map((stored) => stored.request)
    if (listed.length === 0) {
      return HttpResponse.json({ event_requests: [], message: NO_REQUESTS_MESSAGE })
    }
    return HttpResponse.json({ event_requests: listed })
  }),
]
