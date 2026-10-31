import { ROLE } from '@/config/roles'
import {
  assignCoordinator,
  fetchActiveEvents,
  fetchCoordinatorWorkload,
  fetchUnassignedQueue,
  reassignCoordinator,
} from '@/features/lead/api'
import { ApiError, fieldErrorsOf } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { MOCK_ACCOUNTS, mockTokenFor } from '../fixtures/accounts'

/**
 * The Lead mock stands in for SCRUM-95's queue and SCRUM-96's oversight routes, so these tests
 * pin it to what backend/app/modules/events/routes.py and services.py answer on main
 * (ADR-0036, ADR-0041): who may call them, which events each list holds and in what order,
 * and the order the reassignment's refusals come in.
 */

const CHLOE = MOCK_ACCOUNTS.coordinator
const AISHA = MOCK_ACCOUNTS.otherCoordinator

/** The events in the mock, by what makes each one interesting. */
const EVENTS = {
  queuedFirst: 'EVR-MOCK0001',
  queuedSecond: 'EVR-MOCK0002',
  submittedHeldByChloe: 'EVR-LEAD0007',
  underReviewHeldByAisha: 'EVR-LEAD0004',
  awaitingClarificationHeldByChloe: 'EVR-LEAD0005',
  approvedHeldByChloe: 'EVR-LEAD0003',
  safetyReviewHeldByAisha: 'EVR-LEAD0013',
  confirmedHeldByAisha: 'EVR-LEAD0006',
  completedHeldByChloe: 'EVR-LEAD0008',
  cancelledHeldByAisha: 'EVR-LEAD0009',
  rejectedHeldByChloe: 'EVR-LEAD0010',
  draft: 'EVR-LEAD0011',
  cancelledUnheld: 'EVR-LEAD0012',
} as const

const UNKNOWN_REFERENCE = 'EVR-NOSUCH00'
const UNKNOWN_EMAIL = 'nobody@example.com'

async function errorOf(promise: Promise<unknown>): Promise<ApiError> {
  const error: unknown = await promise.then(
    () => null,
    (caught: unknown) => caught,
  )
  if (!(error instanceof ApiError)) {
    throw new Error('Expected the request to fail with an ApiError.')
  }
  return error
}

/** The status, error code, message and field errors a refused call came back with. */
async function refusalOf(promise: Promise<unknown>) {
  const error = await errorOf(promise)
  return {
    status: error.status,
    code: error.code,
    message: error.message,
    fields: fieldErrorsOf(error),
  }
}

async function activeReferences(): Promise<string[]> {
  const { event_requests: rows } = await fetchActiveEvents()
  return rows.map((row) => row.reference)
}

/**
 * Each coordinator's name with the count the mock sends for them and the references of the events
 * they hold, in the mock's order.
 */
async function workloadByName() {
  const { coordinators } = await fetchCoordinatorWorkload()
  return coordinators.map((entry) => ({
    coordinator: entry.coordinator,
    count: entry.active_count,
    references: entry.event_requests.map((row) => row.reference),
  }))
}

/** The Event Coordinators who hold no event in the Lead mock, listed after Aisha and Chloe. */
const IDLE_WORKLOADS = ['Colin Tay', 'Daniel Ong', 'Hana Yusof', 'Priya Nair'].map((name) => ({
  coordinator: name,
  count: 0,
  references: [],
}))

function reassign(reference: string, email: string) {
  return reassignCoordinator({ reference, coordinator_email: email })
}

const THE_LEADS_ROUTES = {
  'the active list': () => fetchActiveEvents(),
  'the workload': () => fetchCoordinatorWorkload(),
  'a reassignment': () => reassign(EVENTS.approvedHeldByChloe, AISHA.email),
}

const OTHER_ROLES = Object.values(MOCK_ACCOUNTS).filter(
  (account) => account.role !== ROLE.EVENT_COORDINATOR_LEAD,
)

beforeEach(() => {
  sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.lead))
})

describe('SCRUM-96 Lead mock: who may use the oversight routes', () => {
  it.each(Object.entries(THE_LEADS_ROUTES))('refuses a visitor %s with 401', async (_, call) => {
    sendRequestsAs(null)

    expect(await refusalOf(call())).toEqual({
      status: 401,
      code: 'authentication_error',
      message: 'Missing, invalid or expired token.',
      fields: {},
    })
  })

  it.each(OTHER_ROLES.map((account) => [account.role, account.email, account] as const))(
    'refuses a signed-in %s (%s) every oversight route with 403, and moves nothing',
    async (_, __, account) => {
      sendRequestsAs(mockTokenFor(account))

      for (const call of Object.values(THE_LEADS_ROUTES)) {
        expect(await refusalOf(call())).toEqual({
          status: 403,
          code: 'authorization_error',
          message: 'You do not have permission to perform this action.',
          fields: {},
        })
      }
      sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.lead))
      const approved = (await fetchActiveEvents()).event_requests.find(
        (row) => row.reference === EVENTS.approvedHeldByChloe,
      )
      expect(approved?.coordinator).toBe(CHLOE.full_name)
    },
  )
})

describe('SCRUM-96 Lead mock: the active list and the workload', () => {
  it('lists every held event in an active status, newest first, and nothing else (ADR-0120)', async () => {
    expect(await activeReferences()).toEqual([
      EVENTS.submittedHeldByChloe,
      EVENTS.awaitingClarificationHeldByChloe,
      EVENTS.underReviewHeldByAisha,
      EVENTS.safetyReviewHeldByAisha,
      EVENTS.approvedHeldByChloe,
      EVENTS.confirmedHeldByAisha,
    ])
  })

  it('shows each active event with the list fields, its status and its coordinator by name', async () => {
    const body = await fetchActiveEvents()

    expect(body).not.toHaveProperty('message')
    expect(
      body.event_requests.find((row) => row.reference === EVENTS.confirmedHeldByAisha),
    ).toEqual({
      reference: EVENTS.confirmedHeldByAisha,
      name: 'Year-End Volunteer Fair',
      proposed_date: '2026-12-14',
      end_date: '2026-12-15',
      start_time: '09:00:00',
      end_time: '17:00:00',
      status: 'confirmed',
      coordinator: 'Aisha Karim',
    })
  })

  it('lists each Event Coordinator by name, with their active events newest first and their count', async () => {
    const body = await fetchCoordinatorWorkload()

    expect(body).not.toHaveProperty('message')
    expect(await workloadByName()).toEqual([
      {
        coordinator: 'Aisha Karim',
        count: 3,
        references: [
          EVENTS.underReviewHeldByAisha,
          EVENTS.safetyReviewHeldByAisha,
          EVENTS.confirmedHeldByAisha,
        ],
      },
      {
        coordinator: 'Chloe Lim',
        count: 3,
        references: [
          EVENTS.submittedHeldByChloe,
          EVENTS.awaitingClarificationHeldByChloe,
          EVENTS.approvedHeldByChloe,
        ],
      },
      ...IDLE_WORKLOADS,
    ])
    expect(body.coordinators[0]?.event_requests[0]).toEqual({
      reference: EVENTS.underReviewHeldByAisha,
      name: 'Quarterly Town Hall',
      proposed_date: '2026-11-28',
      end_date: null,
      start_time: '10:00:00',
      end_time: '12:00:00',
      status: 'under_review',
    })
  })

  it('sends an Event Coordinator who holds nothing with a count of 0 and no events (AC3)', async () => {
    const { coordinators } = await fetchCoordinatorWorkload()

    expect(coordinators.find((entry) => entry.coordinator === 'Colin Tay')).toEqual({
      coordinator: 'Colin Tay',
      active_count: 0,
      event_requests: [],
    })
  })

  it('keeps a coordinator whose every event was moved away, now with 0', async () => {
    for (const reference of [
      EVENTS.underReviewHeldByAisha,
      EVENTS.safetyReviewHeldByAisha,
      EVENTS.confirmedHeldByAisha,
    ]) {
      await reassign(reference, CHLOE.email)
    }

    const [aisha, chloe] = await workloadByName()

    expect(aisha).toEqual({ coordinator: 'Aisha Karim', count: 0, references: [] })
    expect(chloe?.count).toBe(6)
  })

  it('keeps the queue to submitted requests nobody holds, oldest first', async () => {
    const { event_requests: rows } = await fetchUnassignedQueue()

    expect(rows.map((row) => row.reference)).toEqual([EVENTS.queuedFirst, EVENTS.queuedSecond])
  })

  it('sends each queued request with its status, as the backend does (SCRUM-24 AC8)', async () => {
    const { event_requests: rows } = await fetchUnassignedQueue()

    expect(rows.map((row) => row.status)).toEqual(['submitted', 'submitted'])
  })

  it('moves a request assigned from the queue into its coordinator’s workload and the active list', async () => {
    expect(await activeReferences()).not.toContain(EVENTS.queuedSecond)

    await assignCoordinator({ reference: EVENTS.queuedSecond, coordinator_email: AISHA.email })

    expect(await workloadByName()).toContainEqual({
      coordinator: 'Aisha Karim',
      count: 4,
      references: [
        EVENTS.queuedSecond,
        EVENTS.underReviewHeldByAisha,
        EVENTS.safetyReviewHeldByAisha,
        EVENTS.confirmedHeldByAisha,
      ],
    })
    const assigned = (await fetchActiveEvents()).event_requests.find(
      (row) => row.reference === EVENTS.queuedSecond,
    )
    expect(assigned?.coordinator).toBe('Aisha Karim')
    expect(assigned?.status).toBe('submitted')
  })
})

describe('SCRUM-96 Lead mock: reassigning an event', () => {
  it('moves the event to the coordinator named by email and answers with their contact', async () => {
    const moved = await reassign(EVENTS.approvedHeldByChloe, AISHA.email)

    expect(moved).toEqual({
      reference: EVENTS.approvedHeldByChloe,
      name: 'Harbourfront Gala Dinner',
      status: 'approved',
      coordinator: { full_name: 'Aisha Karim', email: 'aisha@connectsphere.test' },
    })
    expect(await workloadByName()).toEqual([
      {
        coordinator: 'Aisha Karim',
        count: 4,
        references: [
          EVENTS.underReviewHeldByAisha,
          EVENTS.safetyReviewHeldByAisha,
          EVENTS.approvedHeldByChloe,
          EVENTS.confirmedHeldByAisha,
        ],
      },
      {
        coordinator: 'Chloe Lim',
        count: 2,
        references: [EVENTS.submittedHeldByChloe, EVENTS.awaitingClarificationHeldByChloe],
      },
      ...IDLE_WORKLOADS,
    ])
  })

  it.each([
    EVENTS.submittedHeldByChloe,
    EVENTS.awaitingClarificationHeldByChloe,
    EVENTS.approvedHeldByChloe,
  ])('reassigns Chloe’s %s, whatever its active status', async (reference) => {
    const moved = await reassign(reference, AISHA.email)

    expect(moved.coordinator.full_name).toBe('Aisha Karim')
  })

  it.each([
    EVENTS.underReviewHeldByAisha,
    EVENTS.safetyReviewHeldByAisha,
    EVENTS.confirmedHeldByAisha,
  ])('reassigns Aisha’s %s, whatever its active status', async (reference) => {
    const moved = await reassign(reference, CHLOE.email)

    expect(moved.coordinator.full_name).toBe('Chloe Lim')
  })

  it('matches the email and the reference ignoring case', async () => {
    const moved = await reassign(
      EVENTS.approvedHeldByChloe.toLowerCase(),
      'AISHA@ConnectSphere.TEST',
    )

    expect(moved.coordinator.email).toBe('aisha@connectsphere.test')
  })

  it('answers a missing email with the payload 400 before it looks up the reference', async () => {
    // JSON.stringify drops an undefined value, so the body reaches the mock without the key.
    const missing = reassign(UNKNOWN_REFERENCE, undefined as unknown as string) // -- the field left out on purpose

    expect(await refusalOf(missing)).toEqual({
      status: 400,
      code: 'validation_error',
      message: 'Invalid request.',
      fields: { coordinator_email: ['Missing data for required field.'] },
    })
  })

  it('answers an email that is not an address with the payload 400 before the reference', async () => {
    expect(await refusalOf(reassign(UNKNOWN_REFERENCE, 'not-an-email'))).toEqual({
      status: 400,
      code: 'validation_error',
      message: 'Invalid request.',
      fields: { coordinator_email: ['Not a valid email address.'] },
    })
  })

  it.each([UNKNOWN_REFERENCE, EVENTS.draft])(
    'answers %s with 404 even when the email is also wrong',
    async (reference) => {
      expect(await refusalOf(reassign(reference, UNKNOWN_EMAIL))).toEqual({
        status: 404,
        code: 'not_found',
        message: 'Event request not found.',
        fields: {},
      })
    },
  )

  it.each([EVENTS.queuedFirst, EVENTS.cancelledUnheld])(
    'refuses %s, which nobody holds, with 409 before it reads the email',
    async (reference) => {
      expect(await refusalOf(reassign(reference, UNKNOWN_EMAIL))).toEqual({
        status: 409,
        code: 'request_not_reassignable',
        message: 'This event request has no coordinator to reassign from.',
        fields: {},
      })
    },
  )

  it.each([EVENTS.completedHeldByChloe, EVENTS.cancelledHeldByAisha, EVENTS.rejectedHeldByChloe])(
    'refuses %s, which is no longer active, with 409 before it reads the email',
    async (reference) => {
      expect(await refusalOf(reassign(reference, UNKNOWN_EMAIL))).toEqual({
        status: 409,
        code: 'request_not_reassignable',
        message:
          'Only a submitted, under-review, awaiting-clarification, approved, safety-review or confirmed event request can be reassigned.',
        fields: {},
      })
    },
  )

  it.each([UNKNOWN_EMAIL, MOCK_ACCOUNTS.lead.email, MOCK_ACCOUNTS.organiser.email])(
    'answers %s, which is no Event Coordinator’s, with a 400 on coordinator_email',
    async (email) => {
      expect(await refusalOf(reassign(EVENTS.approvedHeldByChloe, email))).toEqual({
        status: 400,
        code: 'validation_error',
        message: 'Invalid request.',
        fields: { coordinator_email: ['No Event Coordinator has this email address.'] },
      })
    },
  )

  it('refuses to reassign an event to the coordinator who already holds it', async () => {
    expect(await refusalOf(reassign(EVENTS.approvedHeldByChloe, CHLOE.email))).toEqual({
      status: 409,
      code: 'conflict',
      message: 'That coordinator is already assigned to this event request.',
      fields: {},
    })
  })
})

describe('SCRUM-95 Lead mock: assigning from the queue, on the shared events', () => {
  it('refuses a request that already has a coordinator with 409 before it reads the email', async () => {
    const assign = assignCoordinator({
      reference: EVENTS.submittedHeldByChloe,
      coordinator_email: UNKNOWN_EMAIL,
    })

    expect(await refusalOf(assign)).toEqual({
      status: 409,
      code: 'conflict',
      message: 'This event request already has a coordinator.',
      fields: {},
    })
  })

  it('refuses a request nobody holds that is no longer submitted with its own 409', async () => {
    const assign = assignCoordinator({
      reference: EVENTS.cancelledUnheld,
      coordinator_email: UNKNOWN_EMAIL,
    })

    expect(await refusalOf(assign)).toEqual({
      status: 409,
      code: 'request_not_assignable',
      message: 'Only a submitted event request can be assigned to a coordinator.',
      fields: {},
    })
  })

  it('cannot find a draft, even with a wrong email', async () => {
    const assign = assignCoordinator({ reference: EVENTS.draft, coordinator_email: UNKNOWN_EMAIL })

    expect((await refusalOf(assign)).status).toBe(404)
  })

  it('answers an email that is not an address with the payload 400', async () => {
    const assign = assignCoordinator({
      reference: EVENTS.queuedFirst,
      coordinator_email: 'not-an-email',
    })

    expect((await refusalOf(assign)).fields).toEqual({
      coordinator_email: ['Not a valid email address.'],
    })
  })
})
