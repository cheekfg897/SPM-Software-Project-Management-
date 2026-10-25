import { ROLE } from '@/config/roles'
import type { Role } from '@/config/roles'
import { recordEquipmentOutcome } from '@/features/equipment/api'
import { fetchAssignedEventRequests, fetchEventRequest } from '@/features/eventRequests/api'
import { refusal } from '@/test/refusal'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { MOCK_ACCOUNTS, mockTokenFor } from '../fixtures/accounts'
import type { MockAccount } from '../fixtures/accounts'

/**
 * The mock of a coordinator's assigned events (GET /api/events/requests/assigned) and of an
 * event's record (GET /api/events/requests/<reference>), pinned to what the backend sends
 * (SCRUM-24 AC2, AC9, AC10, AC11; ADR-0026, ADR-0034, ADR-0056). The integration tests check the
 * same shapes against the running backend.
 */

const COORDINATORS_UNDER_REVIEW = 'EVR-7K2M9QXA'
const COORDINATORS_AWAITING_ANSWER = 'EVR-B6YF2K8V'
const ANOTHER_COORDINATORS = 'EVR-W9CR5E7M'
const ANOTHER_COORDINATORS_REJECTED = 'EVR-M1XJ7T3D'
const UNASSIGNED = 'EVR-Q4ZT6N1B'
const NOT_FOUND = { status: 404, code: 'not_found', message: 'Event request not found.' }
const NOT_PERMITTED = { status: 403, code: 'authorization_error' }

function signInAs(account: MockAccount | null) {
  sendRequestsAs(account === null ? null : mockTokenFor(account))
}

/** Every mock account whose role isn't in `allowed`, so a role added later is refused too. */
function accountsOutside(allowed: readonly Role[]): [string, MockAccount][] {
  const outside: [string, MockAccount][] = []
  for (const [name, account] of Object.entries(MOCK_ACCOUNTS)) {
    if (!allowed.includes(account.role)) {
      outside.push([name, account])
    }
  }
  return outside
}

describe('SCRUM-24 mock of a coordinator assigned events', () => {
  it('lists only the events assigned to the coordinator, newest first', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    const list = await fetchAssignedEventRequests()

    // Another coordinator's events and the unassigned ones are newer than some of these, so
    // leaking any of them would show in the order.
    expect(list.event_requests.map((row) => row.reference)).toEqual([
      COORDINATORS_UNDER_REVIEW,
      'EVR-BOOK0101',
      'EVR-MOCK0001',
      'EVR-BOOK0102',
      COORDINATORS_AWAITING_ANSWER,
    ])
    expect(list).not.toHaveProperty('message')
  })

  it('gives a coordinator with no events an empty list and the backend message', async () => {
    signInAs(MOCK_ACCOUNTS.freshCoordinator)

    expect(await fetchAssignedEventRequests()).toEqual({
      event_requests: [],
      message: 'No event requests are assigned to you yet.',
    })
  })

  it.each(accountsOutside([ROLE.EVENT_COORDINATOR]))(
    'refuses %s, who is not an Event Coordinator',
    async (_name, account) => {
      signInAs(account)

      expect(await refusal(fetchAssignedEventRequests())).toMatchObject(NOT_PERMITTED)
    },
  )

  it('refuses a visitor who is not signed in', async () => {
    signInAs(null)

    expect(await refusal(fetchAssignedEventRequests())).toMatchObject({
      status: 401,
      code: 'authentication_error',
    })
  })
})

describe('SCRUM-24 mock of an event record', () => {
  it("shows the organiser the request with its coordinator's name and email, and no ids", async () => {
    signInAs(MOCK_ACCOUNTS.organiser)

    const record = await fetchEventRequest(COORDINATORS_UNDER_REVIEW)

    expect(record).toMatchObject({
      reference: COORDINATORS_UNDER_REVIEW,
      status: 'under_review',
      name: 'Partner Summit',
      coordinator: { full_name: 'Chloe Lim', email: 'chloe@connectsphere.test' },
      decision: null,
      clarifications: [],
      programme_notes: 'Keynote at 9:30, breakout rooms after lunch.',
    })
    expect(record.coordinator).not.toHaveProperty('id')
    expect(record).not.toHaveProperty('coordinator_id')
  })

  it('shows a request with no coordinator yet as having none', async () => {
    signInAs(MOCK_ACCOUNTS.organiser)

    const record = await fetchEventRequest('EVR-3HD8PL2W')

    expect(record).toMatchObject({ coordinator: null, decision: null, programme_notes: null })
  })

  it('shows the decision, with who made it by name', async () => {
    signInAs(MOCK_ACCOUNTS.organiser)

    const record = await fetchEventRequest(ANOTHER_COORDINATORS_REJECTED)

    expect(record.decision).toEqual({
      outcome: 'rejected',
      reason: 'The proposed date clashes with the venue refurbishment.',
      decided_by: 'Marcus Tan',
      decided_at: '2026-09-29T15:20:00+08:00',
    })
  })

  it('shows the clarification exchange, oldest first, with an open question unanswered', async () => {
    signInAs(MOCK_ACCOUNTS.organiser)

    const record = await fetchEventRequest(COORDINATORS_AWAITING_ANSWER)

    expect(record.clarifications).toEqual([
      {
        message: 'Will the roadshow need a loading bay for the demo vehicles?',
        requested_by: 'Chloe Lim',
        requested_at: '2026-09-26T10:00:00+08:00',
        response: 'Yes, for two vans between 11am and noon.',
        answered_by: 'Omar Rahman',
        answered_at: '2026-09-26T14:30:00+08:00',
      },
      {
        message: 'Can the start move to 2pm so the vans can unload first?',
        requested_by: 'Chloe Lim',
        requested_at: '2026-09-27T09:15:00+08:00',
        response: null,
        answered_by: null,
        answered_at: null,
      },
    ])
  })

  it('shows a coordinator the same record for an event assigned to them, but for the equipment', async () => {
    signInAs(MOCK_ACCOUNTS.organiser)
    const organisersView = await fetchEventRequest(COORDINATORS_UNDER_REVIEW)
    signInAs(MOCK_ACCOUNTS.coordinator)

    const coordinatorsView = await fetchEventRequest(COORDINATORS_UNDER_REVIEW)

    // Each sees the equipment their own way, checked below.
    expect({ ...coordinatorsView, equipment_lines: [] }).toEqual({
      ...organisersView,
      equipment_lines: [],
    })
  })

  it.each([
    ["another coordinator's event", ANOTHER_COORDINATORS],
    ['an event no coordinator has yet', UNASSIGNED],
  ])('answers a coordinator %s as not found (AC10)', async (_case, reference) => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    expect(await refusal(fetchEventRequest(reference))).toMatchObject(NOT_FOUND)
  })

  it.each(accountsOutside([ROLE.EVENT_ORGANISER, ROLE.EVENT_COORDINATOR]))(
    'refuses %s, who has no event record to open',
    async (_name, account) => {
      signInAs(account)

      expect(await refusal(fetchEventRequest(COORDINATORS_UNDER_REVIEW))).toMatchObject(
        NOT_PERMITTED,
      )
    },
  )
})

describe('SCRUM-37 AC5, SCRUM-48 AC5 mock of the equipment on an event record', () => {
  it("shows the organiser each line's type, quantity, status and quantity provided, and nothing internal", async () => {
    signInAs(MOCK_ACCOUNTS.organiser)

    const record = await fetchEventRequest(COORDINATORS_UNDER_REVIEW)

    expect(record.equipment_lines).toEqual([
      {
        id: 61,
        equipment_type_name: 'Projector',
        quantity: 10,
        status: 'partially_fulfilled',
        provided_quantity: 6,
      },
      {
        id: 62,
        equipment_type_name: 'Microphone',
        quantity: 4,
        status: 'requested',
        provided_quantity: null,
      },
      {
        id: 63,
        equipment_type_name: 'Lectern',
        quantity: 1,
        status: 'fulfilled',
        provided_quantity: 1,
      },
    ])
  })

  it('shows the coordinator each line as staff save it, technical notes included', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    const record = await fetchEventRequest(COORDINATORS_UNDER_REVIEW)

    expect(record.equipment_lines).toEqual([
      {
        id: 61,
        equipment_type_id: 1,
        quantity: 10,
        notes: 'Two at the back of the hall.',
        status: 'partially_fulfilled',
      },
      {
        id: 62,
        equipment_type_id: 2,
        quantity: 4,
        notes: 'Lapel, not handheld.',
        status: 'requested',
      },
      {
        id: 63,
        equipment_type_id: 3,
        quantity: 1,
        notes: 'At the front, stage left.',
        status: 'fulfilled',
      },
    ])
  })

  it("shows only the event's own lines, and none on an event with no equipment", async () => {
    signInAs(MOCK_ACCOUNTS.otherOrganiser)
    const withLines = await fetchEventRequest('EVR-MOCK0001')
    signInAs(MOCK_ACCOUNTS.organiser)

    const withoutLines = await fetchEventRequest(COORDINATORS_AWAITING_ANSWER)

    expect(withLines.equipment_lines.map((line) => line.id)).toEqual([41, 42])
    expect(withoutLines.equipment_lines).toEqual([])
  })

  it('shows the organiser an outcome as soon as Technical Support record it', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)
    await recordEquipmentOutcome('EVR-MOCK0001', {
      lineId: 41,
      body: { provided_quantity: 6, note: 'Two are being repaired.' },
    })
    signInAs(MOCK_ACCOUNTS.otherOrganiser)

    const record = await fetchEventRequest('EVR-MOCK0001')

    expect(record.equipment_lines[0]).toEqual({
      id: 41,
      equipment_type_name: 'Projector',
      quantity: 8,
      status: 'partially_fulfilled',
      provided_quantity: 6,
    })
  })
})
