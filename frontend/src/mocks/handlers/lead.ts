import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'

import { ROLE } from '@/config/roles'
import { isRecord } from '@/lib/isRecord'

import { MOCK_ACCOUNTS } from '../fixtures/accounts'
import { errorResponse, INVALID_TOKEN_MESSAGE, validationError } from '../responses'

import { accountForRequest } from './auth'

/**
 * The Event Coordinator Lead's queue endpoints (SCRUM-95), as the backend answers them: only
 * the Lead may use them, and a request leaves the queue once it has a coordinator.
 */

export const FORBIDDEN_MESSAGE = 'You do not have permission to perform this action.'
export const EMPTY_QUEUE_MESSAGE = 'No event requests are waiting to be assigned.'
export const NOT_A_COORDINATOR_MESSAGE = 'No Event Coordinator has this email address.'
export const NOT_IN_QUEUE_MESSAGE = 'This event request already has a coordinator.'
const NOT_FOUND_MESSAGE = 'Event request not found.'

/** A queued request. The reference is the backend's key for it, and the queue shows it. */
interface QueuedRequest {
  reference: string
  name: string
  proposed_date: string
  start_time: string
  end_time: string
  expected_attendance: number
  submitted_at: string
}

const INITIAL_QUEUE: readonly QueuedRequest[] = [
  {
    reference: 'EVR-MOCK0001',
    name: 'Annual Partner Summit',
    proposed_date: '2026-11-12',
    start_time: '09:00:00',
    end_time: '17:00:00',
    expected_attendance: 250,
    submitted_at: '2026-10-01T09:30:00+08:00',
  },
  {
    reference: 'EVR-MOCK0002',
    name: 'Product Launch Evening',
    proposed_date: '2026-11-20',
    start_time: '18:00:00',
    end_time: '21:30:00',
    expected_attendance: 120,
    submitted_at: '2026-10-02T14:05:00+08:00',
  },
]

let queue: QueuedRequest[] = []

/** Put the queue back as it started, so no test sees a request another test assigned. */
export function resetMockLeadQueue(): void {
  queue = INITIAL_QUEUE.map((request) => ({ ...request }))
}
resetMockLeadQueue()

/** The queue as the backend shows it: the reference, then AC2's six fields. */
function shownInQueue(request: QueuedRequest) {
  return {
    reference: request.reference,
    name: request.name,
    proposed_date: request.proposed_date,
    start_time: request.start_time,
    end_time: request.end_time,
    expected_attendance: request.expected_attendance,
    submitted_at: request.submitted_at,
  }
}

function isLead(request: Request): boolean {
  return accountForRequest(request)?.role === ROLE.EVENT_COORDINATOR_LEAD
}

/** The 401 or 403 the backend's decorators send, or null when the caller is the Lead. */
function refusalFor(request: Request) {
  if (accountForRequest(request) === undefined) {
    return errorResponse(401, 'authentication_error', INVALID_TOKEN_MESSAGE)
  }
  if (!isLead(request)) {
    return errorResponse(403, 'authorization_error', FORBIDDEN_MESSAGE)
  }
  return null
}

async function readEmail(request: Request): Promise<string> {
  const body: unknown = await request.json().catch(() => null)
  if (!isRecord(body) || typeof body.coordinator_email !== 'string') {
    return ''
  }
  return body.coordinator_email.trim().toLowerCase()
}

/** A reference the queue started with, so one that has left it is a 409 rather than a 404. */
function wasEverQueued(reference: string): boolean {
  return INITIAL_QUEUE.some((request) => request.reference === reference)
}

function coordinatorWithEmail(email: string) {
  return Object.values(MOCK_ACCOUNTS).find(
    (account) => account.role === ROLE.EVENT_COORDINATOR && account.email === email,
  )
}

export const leadHandlers: RequestHandler[] = [
  http.get('/api/events/requests/unassigned', ({ request }) => {
    const refusal = refusalFor(request)
    if (refusal !== null) {
      return refusal
    }
    if (queue.length === 0) {
      return HttpResponse.json({ event_requests: [], message: EMPTY_QUEUE_MESSAGE })
    }
    return HttpResponse.json({ event_requests: queue.map(shownInQueue) })
  }),

  http.post('/api/events/requests/:reference/coordinator', async ({ request, params }) => {
    const refusal = refusalFor(request)
    if (refusal !== null) {
      return refusal
    }
    // The backend's order: reference 404, not-waiting 409, then the email 400 last, so a
    // refused assignment never reveals which addresses belong to coordinators.
    const queued = queue.find((candidate) => candidate.reference === params.reference)
    if (queued === undefined) {
      return wasEverQueued(String(params.reference))
        ? errorResponse(409, 'conflict', NOT_IN_QUEUE_MESSAGE)
        : errorResponse(404, 'not_found', NOT_FOUND_MESSAGE)
    }
    const coordinator = coordinatorWithEmail(await readEmail(request))
    if (coordinator === undefined) {
      return validationError({ coordinator_email: [NOT_A_COORDINATOR_MESSAGE] })
    }
    queue = queue.filter((candidate) => candidate !== queued)
    // Reduced on purpose: the real route also sends the rest of the EventRequestSchema dump
    // (status, dates, and so on), which this omits. The web app reads only the three fields
    // given here, and src/integration/lead.int.test.ts is what pins the real response shape.
    return HttpResponse.json({
      reference: queued.reference,
      name: queued.name,
      coordinator: { full_name: coordinator.full_name, email: coordinator.email },
    })
  }),
]
