import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import type { EventRequestStatus } from '@/config/eventStatus'
import { fetchEventRequestsWithEquipment } from '@/features/eventRequests/api'
import { fetchEquipmentAwaitingAction, fetchEquipmentTypes } from '@/features/techSupport/api'
import { refusal } from '@/test/refusal'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { MOCK_ACCOUNTS, mockTokenFor } from '../fixtures/accounts'
import type { MockAccount } from '../fixtures/accounts'

import { MOCK_TODAY } from './catalogueFixtures'
import { awaitingRow, withEquipmentBody } from './techSupport'

/**
 * The mock of Technical Support's two lists, pinned to what the backend sends: the equipment
 * awaiting action (GET /api/events/requests/awaiting-equipment; SCRUM-38, ADR-0022) and the
 * events with equipment (GET /api/events/requests/with-equipment; SCRUM-24 AC5, AC11), and of
 * the equipment types their lines are named from (GET /api/equipment/types; ADR-0061). The
 * integration tests check the same shapes against the running backend.
 */

const NOT_ALLOWED = { status: 403, code: 'authorization_error' }
const NOT_SIGNED_IN = { status: 401, code: 'authentication_error' }

/** Staff other than Technical Support, and the external roles: none may read either list. */
const NOT_TECHNICAL_SUPPORT: readonly [string, MockAccount][] = [
  ['an Event Coordinator', MOCK_ACCOUNTS.coordinator],
  ['the Event Coordinator Lead', MOCK_ACCOUNTS.lead],
  ['Venue Staff', MOCK_ACCOUNTS.venueStaff],
  ['the Safety Officer', MOCK_ACCOUNTS.safetyOfficer],
  ['an Event Organiser', MOCK_ACCOUNTS.organiser],
  ['an Attendee', MOCK_ACCOUNTS.attendee],
]

/**
 * Every status the queue still lets through: the backend drops only completed, cancelled and
 * rejected events (EQUIPMENT_NOT_NEEDED_STATUSES), written out here so the test doesn't copy the
 * mock's list. Built from the statuses, so one added later is checked too.
 */
const WONT_RUN: readonly string[] = ['completed', 'cancelled', 'rejected']
const STILL_NEEDED: EventRequestStatus[] = Object.values(EVENT_REQUEST_STATUS).filter(
  (status) => !WONT_RUN.includes(status),
)

function signInAs(account: MockAccount | null) {
  sendRequestsAs(account === null ? null : mockTokenFor(account))
}

describe('SCRUM-38 mock of the equipment awaiting action', () => {
  it('lists every upcoming event with a line still requested, soonest first', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    const queue = await fetchEquipmentAwaitingAction()

    // Left out: yesterday's event, the cancelled, completed and rejected ones dated just after
    // today, the event whose lines are all dealt with, and the event with no equipment.
    // On 10 November an earlier start comes first, then the lower id (AC3, ADR-0022).
    expect(queue.equipment_requests.map((row) => row.event.reference)).toEqual([
      'EVR-TECH0001',
      'EVR-MOCK0001',
      'EVR-TECH0002',
      'EVR-TECH0003',
      'EVR-TECH0004',
      'EVR-BOOK0101',
      'EVR-BOOK0102',
    ])
  })

  it('counts whole days to the event from the mock today, 0 on the day itself', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    const queue = await fetchEquipmentAwaitingAction()

    expect(queue.equipment_requests.map((row) => row.days_remaining)).toEqual([
      0, 7, 25, 29, 36, 36, 36,
    ])
  })

  it("shows each event's name, dates and times, and only its lines still requested", async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    const queue = await fetchEquipmentAwaitingAction()

    const careersFair = queue.equipment_requests[5]
    expect(careersFair).toEqual({
      event: {
        reference: 'EVR-BOOK0101',
        name: 'Harbourfront Careers Fair',
        proposed_date: '2026-11-10',
        end_date: '2026-11-10',
        start_time: '09:00:00',
        end_time: '17:00:00',
      },
      // Its fulfilled projector line, added first, is left out (AC4).
      equipment_lines: [
        { id: 292, equipment_type_id: 2, quantity: 6, notes: null, status: 'requested' },
      ],
      days_remaining: 36,
    })
  })

  it.each(STILL_NEEDED)(
    'queues an upcoming %s event whose line is still requested (AC1)',
    (status) => {
      const row = awaitingRow({
        id: 99,
        createdAt: '2026-10-01T00:00:00+00:00',
        event: {
          reference: 'EVR-STATUS99',
          name: 'Status Check',
          status,
          proposed_date: MOCK_TODAY,
          end_date: MOCK_TODAY,
          start_time: '10:00:00',
          end_time: '11:00:00',
        },
        lines: [{ id: 991, equipment_type_id: 1, quantity: 1, notes: null, status: 'requested' }],
      })

      expect(row?.event.reference).toBe('EVR-STATUS99')
    },
  )

  it('keeps an event with several requested lines as one row, its lines in the order added', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    const queue = await fetchEquipmentAwaitingAction()

    const showcase = queue.equipment_requests[1]
    expect(showcase?.equipment_lines.map((line) => line.id)).toEqual([231, 232])
  })

  it.each(NOT_TECHNICAL_SUPPORT)('refuses %s', async (_role, account) => {
    signInAs(account)

    expect(await refusal(fetchEquipmentAwaitingAction())).toMatchObject(NOT_ALLOWED)
  })

  it('refuses a visitor who is not signed in', async () => {
    signInAs(null)

    expect(await refusal(fetchEquipmentAwaitingAction())).toMatchObject(NOT_SIGNED_IN)
  })
})

describe('SCRUM-24 AC5 mock of the events with equipment', () => {
  it('lists every event with an equipment line, whatever its status or date, newest first', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    const list = await fetchEventRequestsWithEquipment()

    // The newest event has no equipment, so leaking it would show first.
    expect(list.event_requests.map((row) => row.reference)).toEqual([
      'EVR-TECH0007',
      'EVR-TECH0006',
      'EVR-7K2M9QXA',
      'EVR-TECH0005',
      'EVR-BOOK0101',
      'EVR-TECH0001',
      'EVR-MOCK0002',
      'EVR-MOCK0001',
      'EVR-TECH0004',
      'EVR-TECH0003',
      'EVR-TECH0002',
      'EVR-BOOK0102',
    ])
    expect(list).not.toHaveProperty('message')
  })

  it("shows only each event's name, dates, times and status (AC8)", async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    const list = await fetchEventRequestsWithEquipment()

    expect(list.event_requests[0]).toEqual({
      reference: 'EVR-TECH0007',
      name: 'Long-Service Awards',
      proposed_date: '2026-10-04',
      end_date: '2026-10-04',
      start_time: '18:00:00',
      end_time: '21:00:00',
      status: 'confirmed',
    })
  })

  it("answers an empty list with the backend's message (AC11)", () => {
    expect(withEquipmentBody([])).toEqual({
      event_requests: [],
      message: 'No events have an equipment request yet.',
    })
  })

  it.each(NOT_TECHNICAL_SUPPORT)('refuses %s', async (_role, account) => {
    signInAs(account)

    expect(await refusal(fetchEventRequestsWithEquipment())).toMatchObject(NOT_ALLOWED)
  })

  it('refuses a visitor who is not signed in', async () => {
    signInAs(null)

    expect(await refusal(fetchEventRequestsWithEquipment())).toMatchObject(NOT_SIGNED_IN)
  })
})

describe('mock of the equipment types the queue is named from', () => {
  it.each([
    ['Technical Support', MOCK_ACCOUNTS.technicalSupport],
    ['an Event Coordinator', MOCK_ACCOUNTS.coordinator],
    ['the Event Coordinator Lead', MOCK_ACCOUNTS.lead],
    ['Venue Staff', MOCK_ACCOUNTS.venueStaff],
    ['the Safety Officer', MOCK_ACCOUNTS.safetyOfficer],
  ])('lists every type by name for %s', async (_role, account) => {
    signInAs(account)

    expect(await fetchEquipmentTypes()).toEqual([
      {
        id: 2,
        name: 'Microphone',
        description: null,
        total_quantity: 12,
        venue_id: null,
        store_name: null,
      },
      {
        id: 1,
        name: 'Projector',
        description: null,
        total_quantity: 6,
        venue_id: null,
        store_name: null,
      },
    ])
  })

  it.each([
    ['an Event Organiser', MOCK_ACCOUNTS.organiser],
    ['an Attendee', MOCK_ACCOUNTS.attendee],
  ])('refuses %s', async (_role, account) => {
    signInAs(account)

    expect(await refusal(fetchEquipmentTypes())).toMatchObject(NOT_ALLOWED)
  })

  it('refuses a visitor who is not signed in', async () => {
    signInAs(null)

    expect(await refusal(fetchEquipmentTypes())).toMatchObject(NOT_SIGNED_IN)
  })
})
