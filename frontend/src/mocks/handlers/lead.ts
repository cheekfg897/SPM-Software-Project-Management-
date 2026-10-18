import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'

import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import type { EventRequestStatus } from '@/config/eventStatus'
import { ROLE } from '@/config/roles'

import { MOCK_ACCOUNTS } from '../fixtures/accounts'
import type { MockAccount } from '../fixtures/accounts'
import {
  errorResponse,
  notAllowed,
  notAuthenticated,
  readBody,
  validationError,
} from '../responses'

import { accountForRequest } from './auth'

/**
 * The Event Coordinator Lead's endpoints, as the backend on main answers them: the queue and the
 * first assignment (SCRUM-95, ADR-0036), and the active list, the workload and reassignment
 * (SCRUM-96, ADR-0041). Only the Lead may use them. One store of events lies behind all five, so
 * a request assigned from the queue joins its coordinator's workload, as it does on the backend.
 */

export const EMPTY_QUEUE_MESSAGE = 'No event requests are waiting to be assigned.'
const NO_ACTIVE_EVENTS_MESSAGE = 'There are no active event requests.'
const NO_WORKLOAD_MESSAGE = 'No coordinator has an active event request.'
export const NOT_A_COORDINATOR_MESSAGE = 'No Event Coordinator has this email address.'
const ALREADY_HAS_COORDINATOR_MESSAGE = 'This event request already has a coordinator.'
const NOT_ASSIGNABLE_MESSAGE = 'Only a submitted event request can be assigned to a coordinator.'
export const ALREADY_ASSIGNED_MESSAGE =
  'That coordinator is already assigned to this event request.'
const NO_COORDINATOR_TO_REPLACE_MESSAGE = 'This event request has no coordinator to reassign from.'
const NOT_REASSIGNABLE_MESSAGE =
  'Only a submitted, under-review, awaiting-clarification, approved, safety-review or ' +
  'confirmed event request can be reassigned.'
const NOT_FOUND_MESSAGE = 'Event request not found.'
const MISSING_EMAIL_MESSAGE = 'Missing data for required field.'
const INVALID_EMAIL_MESSAGE = 'Not a valid email address.'

/** Close enough to marshmallow's Email field for the addresses tests send. */
const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/

/** The backend's ACTIVE_STATUSES (ADR-0041 decision 2). */
const ACTIVE_STATUSES: readonly EventRequestStatus[] = [
  EVENT_REQUEST_STATUS.SUBMITTED,
  EVENT_REQUEST_STATUS.UNDER_REVIEW,
  EVENT_REQUEST_STATUS.AWAITING_CLARIFICATION,
  EVENT_REQUEST_STATUS.APPROVED,
  EVENT_REQUEST_STATUS.SAFETY_REVIEW,
  EVENT_REQUEST_STATUS.CONFIRMED,
]

/** An event as the backend stores it, with its coordinator as an id it never sends. */
interface LeadMockEvent {
  reference: string
  name: string
  status: EventRequestStatus
  proposed_date: string
  end_date: string | null
  start_time: string
  end_time: string
  expected_attendance: number
  /** When it was saved; the queue shows it as `submitted_at`, and the lists sort by it. */
  created_at: string
  coordinator_id: number | null
}

const CHLOE_ID = MOCK_ACCOUNTS.coordinator.id
const AISHA_ID = MOCK_ACCOUNTS.otherCoordinator.id

/** A whole day, for the events whose times don't matter to any test. */
const ALL_DAY = { end_date: null, start_time: '09:00:00', end_time: '17:00:00' } as const

/**
 * Saved out of date order on purpose, so only sorting by when they were saved puts them in the
 * backend's order. The events that are not active are the newest, where a list that forgot to
 * leave them out would show them first; the cancelled one nobody holds is the oldest, where a
 * queue that forgot the status would show it first.
 */
const INITIAL_EVENTS: readonly LeadMockEvent[] = [
  {
    reference: 'EVR-MOCK0001',
    name: 'Annual Partner Summit',
    status: EVENT_REQUEST_STATUS.SUBMITTED,
    proposed_date: '2026-11-12',
    ...ALL_DAY,
    expected_attendance: 250,
    created_at: '2026-10-01T09:30:00+08:00',
    coordinator_id: null,
  },
  {
    reference: 'EVR-LEAD0003',
    name: 'Harbourfront Gala Dinner',
    status: EVENT_REQUEST_STATUS.APPROVED,
    proposed_date: '2026-12-05',
    end_date: null,
    start_time: '19:00:00',
    end_time: '23:00:00',
    expected_attendance: 180,
    created_at: '2026-09-12T10:00:00+08:00',
    coordinator_id: CHLOE_ID,
  },
  {
    reference: 'EVR-LEAD0010',
    name: 'Startup Pitch Day',
    status: EVENT_REQUEST_STATUS.REJECTED,
    proposed_date: '2026-11-30',
    ...ALL_DAY,
    expected_attendance: 90,
    created_at: '2026-10-06T10:00:00+08:00',
    coordinator_id: CHLOE_ID,
  },
  {
    reference: 'EVR-MOCK0002',
    name: 'Product Launch Evening',
    status: EVENT_REQUEST_STATUS.SUBMITTED,
    proposed_date: '2026-11-20',
    end_date: null,
    start_time: '18:00:00',
    end_time: '21:30:00',
    expected_attendance: 120,
    created_at: '2026-10-02T14:05:00+08:00',
    coordinator_id: null,
  },
  {
    reference: 'EVR-LEAD0006',
    name: 'Year-End Volunteer Fair',
    status: EVENT_REQUEST_STATUS.CONFIRMED,
    proposed_date: '2026-12-14',
    end_date: '2026-12-15',
    start_time: '09:00:00',
    end_time: '17:00:00',
    expected_attendance: 400,
    created_at: '2026-09-05T09:00:00+08:00',
    coordinator_id: AISHA_ID,
  },
  {
    reference: 'EVR-LEAD0008',
    name: 'Spring Networking Night',
    status: EVENT_REQUEST_STATUS.COMPLETED,
    proposed_date: '2026-10-10',
    ...ALL_DAY,
    expected_attendance: 60,
    created_at: '2026-10-04T10:00:00+08:00',
    coordinator_id: CHLOE_ID,
  },
  {
    reference: 'EVR-LEAD0005',
    name: 'Founders’ Fireside Chat',
    status: EVENT_REQUEST_STATUS.AWAITING_CLARIFICATION,
    proposed_date: '2026-12-10',
    end_date: null,
    start_time: '17:00:00',
    end_time: '19:00:00',
    expected_attendance: 70,
    created_at: '2026-09-30T16:40:00+08:00',
    coordinator_id: CHLOE_ID,
  },
  {
    reference: 'EVR-LEAD0011',
    name: 'Volunteer Briefing',
    status: EVENT_REQUEST_STATUS.DRAFT,
    proposed_date: '2026-12-01',
    ...ALL_DAY,
    expected_attendance: 30,
    created_at: '2026-10-07T10:00:00+08:00',
    coordinator_id: null,
  },
  {
    reference: 'EVR-LEAD0004',
    name: 'Quarterly Town Hall',
    status: EVENT_REQUEST_STATUS.UNDER_REVIEW,
    proposed_date: '2026-11-28',
    end_date: null,
    start_time: '10:00:00',
    end_time: '12:00:00',
    expected_attendance: 300,
    created_at: '2026-09-25T11:15:00+08:00',
    coordinator_id: AISHA_ID,
  },
  {
    reference: 'EVR-LEAD0009',
    name: 'Riverside Roadshow',
    status: EVENT_REQUEST_STATUS.CANCELLED,
    proposed_date: '2026-11-15',
    ...ALL_DAY,
    expected_attendance: 150,
    created_at: '2026-10-05T10:00:00+08:00',
    coordinator_id: AISHA_ID,
  },
  {
    reference: 'EVR-LEAD0007',
    name: 'Customer Insights Forum',
    status: EVENT_REQUEST_STATUS.SUBMITTED,
    proposed_date: '2026-11-25',
    end_date: null,
    start_time: '14:00:00',
    end_time: '16:30:00',
    expected_attendance: 80,
    created_at: '2026-10-03T08:20:00+08:00',
    coordinator_id: CHLOE_ID,
  },
  {
    reference: 'EVR-LEAD0013',
    name: 'Rooftop Film Night',
    status: EVENT_REQUEST_STATUS.SAFETY_REVIEW,
    proposed_date: '2026-12-08',
    end_date: null,
    start_time: '19:30:00',
    end_time: '22:00:00',
    expected_attendance: 110,
    created_at: '2026-09-20T15:00:00+08:00',
    coordinator_id: AISHA_ID,
  },
  {
    reference: 'EVR-LEAD0012',
    name: 'Lunchtime Workshop',
    status: EVENT_REQUEST_STATUS.CANCELLED,
    proposed_date: '2026-11-05',
    ...ALL_DAY,
    expected_attendance: 40,
    created_at: '2026-09-01T10:00:00+08:00',
    coordinator_id: null,
  },
]

let events: LeadMockEvent[] = []

/** Put the Lead's events back as they started, so no test sees another's assignment. */
export function resetMockLeadQueue(): void {
  events = INITIAL_EVENTS.map((event) => ({ ...event }))
}
resetMockLeadQueue()

/** The 401 or 403 the backend's decorators send, or null when the caller is the Lead. */
function refusalFor(request: Request) {
  const account = accountForRequest(request)
  if (account === undefined) {
    return notAuthenticated()
  }
  if (account.role !== ROLE.EVENT_COORDINATOR_LEAD) {
    return notAllowed()
  }
  return null
}

/** The email the Lead typed, lower-cased, or the payload 400 the backend checks first. */
async function coordinatorEmailOrRefusal(request: Request): Promise<string | Response> {
  const { coordinator_email: email } = await readBody(request)
  if (typeof email !== 'string') {
    return validationError({ coordinator_email: [MISSING_EMAIL_MESSAGE] })
  }
  if (!EMAIL_PATTERN.test(email)) {
    return validationError({ coordinator_email: [INVALID_EMAIL_MESSAGE] })
  }
  return email.toLowerCase()
}

/** The event behind a reference, ignoring case and spaces. Staff never find a draft (ADR-0024). */
function eventByReference(reference: string): LeadMockEvent | undefined {
  const wanted = reference.trim().toUpperCase()
  return events.find(
    (event) => event.reference === wanted && event.status !== EVENT_REQUEST_STATUS.DRAFT,
  )
}

function coordinatorWithEmail(email: string): MockAccount | undefined {
  return Object.values(MOCK_ACCOUNTS).find(
    (account) => account.role === ROLE.EVENT_COORDINATOR && account.email === email,
  )
}

function coordinatorNameOf(coordinatorId: number): string {
  const coordinator = Object.values(MOCK_ACCOUNTS).find((account) => account.id === coordinatorId)
  return coordinator?.full_name ?? ''
}

function isActive(event: LeadMockEvent): boolean {
  return ACTIVE_STATUSES.includes(event.status)
}

function activeNewestFirst(): LeadMockEvent[] {
  const active = events.filter(isActive)
  return active.sort((a, b) => b.created_at.localeCompare(a.created_at))
}

/** The fields every role's list shows: name, date, times and status (SCRUM-24 AC8). */
function listRow(event: LeadMockEvent) {
  return {
    reference: event.reference,
    name: event.name,
    proposed_date: event.proposed_date,
    end_date: event.end_date,
    start_time: event.start_time,
    end_time: event.end_time,
    status: event.status,
  }
}

/** A list under `key`; an empty one also carries the message saying there is nothing in it. */
function listBody(key: string, rows: unknown[], emptyMessage: string) {
  if (rows.length === 0) {
    return HttpResponse.json({ [key]: rows, message: emptyMessage })
  }
  return HttpResponse.json({ [key]: rows })
}

function queueBody() {
  const waiting = events.filter(
    (event) => event.status === EVENT_REQUEST_STATUS.SUBMITTED && event.coordinator_id === null,
  )
  waiting.sort((a, b) => a.created_at.localeCompare(b.created_at))
  const rows = waiting.map((event) => ({
    reference: event.reference,
    name: event.name,
    proposed_date: event.proposed_date,
    start_time: event.start_time,
    end_time: event.end_time,
    expected_attendance: event.expected_attendance,
    submitted_at: event.created_at,
  }))
  return listBody('event_requests', rows, EMPTY_QUEUE_MESSAGE)
}

function activeBody() {
  const rows = activeNewestFirst().map((event) => ({
    ...listRow(event),
    coordinator: event.coordinator_id === null ? null : coordinatorNameOf(event.coordinator_id),
  }))
  return listBody('event_requests', rows, NO_ACTIVE_EVENTS_MESSAGE)
}

/** Each coordinator holding an active event, by name then id, with those events newest first. */
function workloadBody() {
  const heldBy = new Map<number, LeadMockEvent[]>()
  for (const event of activeNewestFirst()) {
    if (event.coordinator_id === null) {
      continue
    }
    const held = heldBy.get(event.coordinator_id) ?? []
    held.push(event)
    heldBy.set(event.coordinator_id, held)
  }
  const workloads = [...heldBy].map(([id, held]) => ({ id, name: coordinatorNameOf(id), held }))
  workloads.sort((a, b) => a.name.localeCompare(b.name) || a.id - b.id)
  const rows = workloads.map((workload) => ({
    coordinator: workload.name,
    event_requests: workload.held.map(listRow),
  }))
  return listBody('coordinators', rows, NO_WORKLOAD_MESSAGE)
}

/**
 * The request and its new coordinator's name and email. Reduced on purpose: the real route also
 * sends the rest of the EventRequestSchema dump (purpose, dates and so on), which the web app
 * doesn't read.
 */
function handedOver(event: LeadMockEvent, coordinator: MockAccount) {
  event.coordinator_id = coordinator.id
  return HttpResponse.json({
    reference: event.reference,
    name: event.name,
    status: event.status,
    coordinator: { full_name: coordinator.full_name, email: coordinator.email },
  })
}

/**
 * The checks both actions start with, in the backend's order: who is asking, then the payload,
 * then the reference. Either the event and the typed email, or the refusal to send.
 */
async function targetOrRefusal(
  request: Request,
  reference: string,
): Promise<{ event: LeadMockEvent; email: string } | Response> {
  const refusal = refusalFor(request)
  if (refusal !== null) {
    return refusal
  }
  const email = await coordinatorEmailOrRefusal(request)
  if (email instanceof Response) {
    return email
  }
  const event = eventByReference(reference)
  if (event === undefined) {
    return errorResponse(404, 'not_found', NOT_FOUND_MESSAGE)
  }
  return { event, email }
}

/** The same 400 for an unknown email and another role's, so neither is revealed (ADR-0021). */
function notACoordinator() {
  return validationError({ coordinator_email: [NOT_A_COORDINATOR_MESSAGE] })
}

export const leadHandlers: RequestHandler[] = [
  http.get('/api/events/requests/unassigned', ({ request }) => {
    return refusalFor(request) ?? queueBody()
  }),

  http.get('/api/events/requests/active', ({ request }) => {
    return refusalFor(request) ?? activeBody()
  }),

  http.get('/api/events/coordinators/workload', ({ request }) => {
    return refusalFor(request) ?? workloadBody()
  }),

  http.post('/api/events/requests/:reference/coordinator', async ({ request, params }) => {
    // The backend's order (ADR-0036 decision 11): the request's own state comes before the
    // email, so a refusal never says which addresses are coordinators'.
    const target = await targetOrRefusal(request, String(params.reference))
    if (target instanceof Response) {
      return target
    }
    const { event, email } = target
    if (event.coordinator_id !== null) {
      return errorResponse(409, 'conflict', ALREADY_HAS_COORDINATOR_MESSAGE)
    }
    if (event.status !== EVENT_REQUEST_STATUS.SUBMITTED) {
      return errorResponse(409, 'request_not_assignable', NOT_ASSIGNABLE_MESSAGE)
    }
    const coordinator = coordinatorWithEmail(email)
    if (coordinator === undefined) {
      return notACoordinator()
    }
    return handedOver(event, coordinator)
  }),

  http.post('/api/events/requests/:reference/reassign', async ({ request, params }) => {
    // The backend's order (ADR-0021, ADR-0041): no coordinator, not active, the email, then the
    // same coordinator.
    const target = await targetOrRefusal(request, String(params.reference))
    if (target instanceof Response) {
      return target
    }
    const { event, email } = target
    if (event.coordinator_id === null) {
      return errorResponse(409, 'request_not_reassignable', NO_COORDINATOR_TO_REPLACE_MESSAGE)
    }
    if (!isActive(event)) {
      return errorResponse(409, 'request_not_reassignable', NOT_REASSIGNABLE_MESSAGE)
    }
    const coordinator = coordinatorWithEmail(email)
    if (coordinator === undefined) {
      return notACoordinator()
    }
    if (coordinator.id === event.coordinator_id) {
      return errorResponse(409, 'conflict', ALREADY_ASSIGNED_MESSAGE)
    }
    return handedOver(event, coordinator)
  }),
]
