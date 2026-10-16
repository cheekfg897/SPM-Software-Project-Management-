import { fetchAssignedEventRequests, fetchEventRequest } from '@/features/eventRequests/api'
import { refusal } from '@/test/refusal'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { MOCK_ACCOUNTS, mockTokenFor } from '../fixtures/accounts'
import type { MockAccount } from '../fixtures/accounts'

/**
 * The mock of a coordinator's assigned events (GET /api/events/requests/assigned) and of an
 * event's record (GET /api/events/requests/<reference>), pinned to what the backend sends
 * (SCRUM-24 AC2, AC9, AC10, AC11; ADR-0026, ADR-0034, ADR-0046). The integration tests check the
 * same shapes against the running backend.
 */

const COORDINATORS_UNDER_REVIEW = 'EVR-7K2M9QXA'
const COORDINATORS_AWAITING_ANSWER = 'EVR-B6YF2K8V'
const ANOTHER_COORDINATORS = 'EVR-W9CR5E7M'
const ANOTHER_COORDINATORS_REJECTED = 'EVR-M1XJ7T3D'
const UNASSIGNED = 'EVR-Q4ZT6N1B'
const NOT_FOUND = { status: 404, code: 'not_found', message: 'Event request not found.' }

function signInAs(account: MockAccount | null) {
  sendRequestsAs(account === null ? null : mockTokenFor(account))
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

  it('refuses an organiser, and a visitor who is not signed in', async () => {
    signInAs(MOCK_ACCOUNTS.organiser)
    const organiser = await refusal(fetchAssignedEventRequests())
    signInAs(null)
    const visitor = await refusal(fetchAssignedEventRequests())

    expect(organiser).toMatchObject({ status: 403, code: 'authorization_error' })
    expect(visitor).toMatchObject({ status: 401, code: 'authentication_error' })
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
      equipment_lines: [],
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

  it('shows a coordinator the same record for an event assigned to them', async () => {
    signInAs(MOCK_ACCOUNTS.organiser)
    const organisersView = await fetchEventRequest(COORDINATORS_UNDER_REVIEW)
    signInAs(MOCK_ACCOUNTS.coordinator)

    const coordinatorsView = await fetchEventRequest(COORDINATORS_UNDER_REVIEW)

    expect(coordinatorsView).toEqual(organisersView)
  })

  it.each([
    ["another coordinator's event", ANOTHER_COORDINATORS],
    ['an event no coordinator has yet', UNASSIGNED],
  ])('answers a coordinator %s as not found (AC10)', async (_case, reference) => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    expect(await refusal(fetchEventRequest(reference))).toMatchObject(NOT_FOUND)
  })

  it.each([
    ['an Attendee', MOCK_ACCOUNTS.attendee],
    ['Venue Staff', MOCK_ACCOUNTS.venueStaff],
    ['the Lead', MOCK_ACCOUNTS.lead],
  ])('refuses %s, who has no event record to open', async (_role, account) => {
    signInAs(account)

    expect(await refusal(fetchEventRequest(COORDINATORS_UNDER_REVIEW))).toMatchObject({
      status: 403,
      code: 'authorization_error',
    })
  })
})
