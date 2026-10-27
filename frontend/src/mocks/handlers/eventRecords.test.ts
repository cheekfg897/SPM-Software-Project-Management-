import { ROLE } from '@/config/roles'
import type { Role } from '@/config/roles'
import { decideBookingRequest, raiseBookingRequest } from '@/features/booking/api'
import { recordEquipmentOutcome, reserveEquipment } from '@/features/equipment/api'
import {
  completeEvent,
  editEventRequest,
  fetchAssignedEventRequests,
  fetchEventRequest,
} from '@/features/eventRequests/api'
import { refusal } from '@/test/refusal'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { MOCK_ACCOUNTS, mockTokenFor } from '../fixtures/accounts'
import type { MockAccount } from '../fixtures/accounts'

import { addToHistory } from './eventHistoryStore'

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
/** Sara's open event, which the equipment mocks keep: two lines, Technical Support reserve for it. */
const WITH_EQUIPMENT = 'EVR-MOCK0001'
/** The request's own fields, as every record sends them. */
const REQUEST_KEYS = [
  'reference',
  'status',
  'name',
  'purpose',
  'description',
  'proposed_date',
  'end_date',
  'start_time',
  'end_time',
  'expected_attendance',
  'venue_requirements',
  'accessibility_needs',
  'equipment_requirements',
  'registration_required',
  'created_at',
]
/** The sections the organiser's and the coordinator's record both send (SCRUM-93 AC5). */
const EVERY_RECORD_KEY = [
  'programme_notes',
  'coordinator',
  'decision',
  'clarifications',
  'equipment_lines',
  'venue_arrangements',
  'safety_outcome',
]
/**
 * What only the organiser's record sends: everything else on it (SCRUM-24 AC10, ADR-0104), but the
 * safety outcome, which the coordinator's sends too (SCRUM-99 AC4, ADR-0113).
 */
const ORGANISERS_OWN_KEYS = ['internal_planning_notes', 'equipment_reservations']
/** A Harbour Gala arrangement as the booking mock saves it, before its own details. */
const GALA_ARRANGEMENT = {
  expected_occupancy: 10,
  required_layout: null,
  justification: null,
  status: 'approved',
  decision_reason: null,
  hold_expires_at: null,
  needs_alternative_venue: false,
  unavailability: [],
  flagged_after_change: false,
  reassessment_flags: [],
  preparation_status: 'not_started',
  preparation_notes: null,
}
/** Boardroom Two as the record names it, with what it offers. */
const BOARDROOM_TWO = {
  venue_name: 'Boardroom Two',
  venue_location: 'Level 3, Tower Block',
  venue_capacity: 20,
  venue_facilities: ['video conferencing'],
  venue_accessibility_features: ['lift access'],
}
/** The Safety Officer's checklist on the mock's recorded outcomes. */
const SAFETY_CHECKLIST = {
  attendance_vs_capacity: '80 expected in a hall for 120.',
  venue_layout: 'Theatre layout with two aisles.',
  emergency_access: 'Both fire exits are clear.',
  accessibility: 'Ramp at the side entrance.',
  equipment_placement: 'Cables taped down along the stage.',
  crowd_movement: 'One-way flow at the doors.',
  venue_restrictions: 'No open flames.',
}
/** The Safety Officer's approval, for a test to add to an event's history. */
const SAFETY_APPROVAL = {
  kind: 'safety_outcome_recorded',
  occurred_at: '2026-10-01T10:00:00+08:00',
  actor_name: MOCK_ACCOUNTS.safetyOfficer.full_name,
  details: { outcome: 'approved', checklist: SAFETY_CHECKLIST, reason: null },
}

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

  it("shows a coordinator the same record for an event assigned to them, but for the organiser's own sections", async () => {
    signInAs(MOCK_ACCOUNTS.organiser)
    const organisersView = await fetchEventRequest(COORDINATORS_UNDER_REVIEW)
    signInAs(MOCK_ACCOUNTS.coordinator)

    const coordinatorsView = await fetchEventRequest(COORDINATORS_UNDER_REVIEW)

    // Each sees the equipment their own way, and only the organiser is sent the rest of the
    // record: all checked below. Both see the safety check (SCRUM-99 AC4).
    expect({ ...coordinatorsView, equipment_lines: [] }).toEqual({
      ...organisersView,
      equipment_lines: [],
      internal_planning_notes: undefined,
      equipment_reservations: undefined,
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

describe('SCRUM-24 AC10 mock of everything on the organiser record, at every stage', () => {
  const CONFIRMED_GALA = 'EVR-BOOK0112'
  const APPROVED_CAREERS_FAIR = 'EVR-BOOK0101'

  it('sends the organiser every section of the record and nothing else', async () => {
    signInAs(MOCK_ACCOUNTS.organiser)

    const record = await fetchEventRequest(COORDINATORS_UNDER_REVIEW)

    expect(Object.keys(record).sort()).toEqual(
      [...REQUEST_KEYS, ...EVERY_RECORD_KEY, ...ORGANISERS_OWN_KEYS].sort(),
    )
  })

  it("sends the coordinator none of the organiser's own sections: they have their own pages", async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    const record = await fetchEventRequest(APPROVED_CAREERS_FAIR)

    expect(Object.keys(record).sort()).toEqual([...REQUEST_KEYS, ...EVERY_RECORD_KEY].sort())
  })

  it('shows the organiser every arrangement in full, earliest first, a withdrawn one too', async () => {
    signInAs(MOCK_ACCOUNTS.otherOrganiser)

    const record = await fetchEventRequest(CONFIRMED_GALA)

    expect(record.venue_arrangements).toEqual([
      {
        ...GALA_ARRANGEMENT,
        ...BOARDROOM_TWO,
        starts_at: '2026-12-05T17:00:00+08:00',
        ends_at: '2026-12-05T18:00:00+08:00',
        purpose: 'Drinks reception',
        decision_reason: 'Booked',
      },
      {
        ...GALA_ARRANGEMENT,
        venue_name: 'Marina Hall',
        venue_location: 'Level 1, Marina Wing',
        // What the Safety Officer reviews of the venue, the organiser sees too (26 Oct).
        venue_capacity: 200,
        venue_facilities: ['projector', 'stage'],
        venue_accessibility_features: ['step-free access', 'hearing loop'],
        starts_at: '2026-12-05T18:00:00+08:00',
        ends_at: '2026-12-05T23:00:00+08:00',
        purpose: 'Gala dinner',
        required_layout: 'banquet',
        decision_reason: 'Booked for the dinner.',
        preparation_status: 'ready',
        preparation_notes: 'Tables set for 80.',
      },
      {
        ...GALA_ARRANGEMENT,
        ...BOARDROOM_TWO,
        starts_at: '2026-12-05T19:00:00+08:00',
        ends_at: '2026-12-05T21:00:00+08:00',
        purpose: 'Overflow room',
        status: 'withdrawn',
      },
    ])
  })

  it('shows an arrangement as soon as it is raised, long before the event is confirmed', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)
    const raised = await raiseBookingRequest(APPROVED_CAREERS_FAIR, {
      venue_id: 1,
      starts_at: '2026-11-10T09:00:00+08:00',
      ends_at: '2026-11-10T12:00:00+08:00',
      purpose: 'Careers fair',
    })
    signInAs(MOCK_ACCOUNTS.otherOrganiser)
    const pending = await fetchEventRequest(APPROVED_CAREERS_FAIR)
    signInAs(MOCK_ACCOUNTS.venueStaff)
    await decideBookingRequest(raised.id, { outcome: 'rejected', reason: 'Hall is closed.' })
    signInAs(MOCK_ACCOUNTS.otherOrganiser)

    const rejected = await fetchEventRequest(APPROVED_CAREERS_FAIR)

    expect(pending.status).toBe('approved')
    expect(pending.venue_arrangements?.map((shown) => shown.status)).toEqual(['pending'])
    expect(rejected.venue_arrangements?.map((shown) => shown.decision_reason)).toEqual([
      'Hall is closed.',
    ])
  })

  it('shows the organiser each equipment line in full: notes, outcome, note and reviewer', async () => {
    signInAs(MOCK_ACCOUNTS.organiser)

    const record = await fetchEventRequest(COORDINATORS_UNDER_REVIEW)

    expect(record.equipment_lines).toEqual([
      {
        equipment_type_name: 'Projector',
        quantity: 10,
        notes: 'Two at the back of the hall.',
        status: 'partially_fulfilled',
        provided_quantity: 6,
        shortfall: 4,
        outcome_note: 'Four are out for repair.',
        reviewed_by: 'Tariq Hassan',
        reviewed_at: '2026-10-05T11:00:00+08:00',
      },
      {
        equipment_type_name: 'Microphone',
        quantity: 4,
        notes: 'Lapel, not handheld.',
        status: 'requested',
        provided_quantity: null,
        shortfall: null,
        outcome_note: null,
        reviewed_by: null,
        reviewed_at: null,
      },
      {
        equipment_type_name: 'Lectern',
        quantity: 1,
        notes: 'At the front, stage left.',
        status: 'fulfilled',
        provided_quantity: 1,
        shortfall: 0,
        outcome_note: 'The spare one, with a reading light.',
        reviewed_by: 'Tariq Hassan',
        reviewed_at: '2026-10-05T11:05:00+08:00',
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

  it('shows the organiser an outcome and a reservation as soon as Technical Support record them', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)
    await recordEquipmentOutcome(WITH_EQUIPMENT, {
      lineId: 41,
      body: { provided_quantity: 6, note: 'Two are being repaired.' },
    })
    await reserveEquipment(WITH_EQUIPMENT, { equipment_type_id: 2, quantity: 4 })
    // A decoy on another event, which this event's record must leave out.
    await reserveEquipment('EVR-APPROVED', { equipment_type_id: 1, quantity: 1 })
    signInAs(MOCK_ACCOUNTS.otherOrganiser)

    const record = await fetchEventRequest(WITH_EQUIPMENT)

    expect(record.equipment_lines[0]).toMatchObject({
      equipment_type_name: 'Projector',
      provided_quantity: 6,
      shortfall: 2,
      outcome_note: 'Two are being repaired.',
      reviewed_by: 'Tariq Hassan',
    })
    expect(record.equipment_reservations).toEqual([
      {
        equipment_type_name: 'Microphone',
        quantity: 4,
        starts_at: expect.any(String) as string,
        ends_at: expect.any(String) as string,
        reserved_by: 'Tariq Hassan',
        preparation_status: 'not_started',
        preparation_notes: null,
      },
    ])
  })

  it('shows the organiser the planning notes the coordinator saved', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)
    await editEventRequest(COORDINATORS_UNDER_REVIEW, { internal_planning_notes: 'Call AV.' })
    signInAs(MOCK_ACCOUNTS.organiser)

    const record = await fetchEventRequest(COORDINATORS_UNDER_REVIEW)

    expect(record.internal_planning_notes).toBe('Call AV.')
  })

  it("shows the organiser the current safety check's outcome, checklist, comments, officer and time", async () => {
    signInAs(MOCK_ACCOUNTS.otherOrganiser)

    const record = await fetchEventRequest('EVR-BOOK0102')

    expect(record.safety_outcome).toEqual({
      outcome: 'approved',
      checklist: SAFETY_CHECKLIST,
      reason: null,
      recorded_by: 'Sana Iyer',
      recorded_at: '2026-10-04T14:00:00+08:00',
      flagged_arrangement_count: 0,
      reopened_line_count: 0,
    })
  })

  it('counts what the officer named to rework, and shows the coordinator the outcome (SCRUM-99 AC4)', async () => {
    // Chloe's EVR-BOOK0101, sent back with changes.
    const careersFair = 'EVR-BOOK0101'
    addToHistory(careersFair, [
      {
        ...SAFETY_APPROVAL,
        details: {
          ...SAFETY_APPROVAL.details,
          outcome: 'changes_requested',
          reason: 'Clear the east exit.',
          flagged_arrangement_ids: [4],
          reopened_line_ids: [7, 8],
        },
      },
    ])
    signInAs(MOCK_ACCOUNTS.coordinator)

    const record = await fetchEventRequest(careersFair)

    expect(record.safety_outcome).toMatchObject({
      outcome: 'changes_requested',
      reason: 'Clear the east exit.',
      flagged_arrangement_count: 1,
      reopened_line_count: 2,
    })
  })

  it('shows a request for changes before the event is confirmed, with its reason', async () => {
    signInAs(MOCK_ACCOUNTS.organiser)

    const record = await fetchEventRequest(ANOTHER_COORDINATORS)

    expect(record.status).toBe('approved')
    expect(record.safety_outcome).toMatchObject({
      outcome: 'changes_requested',
      reason: 'Keep the terrace exit clear during the dinner.',
    })
  })

  it('shows no outcome while the current check has none on record', async () => {
    signInAs(MOCK_ACCOUNTS.otherOrganiser)

    const record = await fetchEventRequest(CONFIRMED_GALA)

    expect(record.safety_outcome).toBeNull()
  })

  it('shows no outcome once a significant edit withdraws the approval (SCRUM-49 AC13)', async () => {
    // Hana's Harbour Lights Concert, approved by the Safety Officer, in Sara's organisation.
    const approved = 'EVR-PLAN0003'
    addToHistory(approved, [SAFETY_APPROVAL])
    signInAs(MOCK_ACCOUNTS.planningCoordinator)
    await editEventRequest(approved, { expected_attendance: 100 })
    signInAs(MOCK_ACCOUNTS.otherOrganiser)

    const record = await fetchEventRequest(approved)

    // The withdrawn approval stays in the history; the check has no outcome until the next one.
    expect(record.status).toBe('approved')
    expect(record.safety_outcome).toBeNull()
  })

  it('keeps showing the outcome once the event is completed', async () => {
    // Hana's Autumn Book Fair, confirmed and already ended, in Sara's organisation.
    const ended = 'EVR-PLAN0005'
    addToHistory(ended, [SAFETY_APPROVAL])
    signInAs(MOCK_ACCOUNTS.planningCoordinator)
    await completeEvent(ended)
    signInAs(MOCK_ACCOUNTS.otherOrganiser)

    const record = await fetchEventRequest(ended)

    expect(record.status).toBe('completed')
    expect(record.safety_outcome).toMatchObject({
      outcome: 'approved',
      recorded_by: MOCK_ACCOUNTS.safetyOfficer.full_name,
      recorded_at: '2026-10-01T10:00:00+08:00',
    })
  })

  it("shows only the event's own lines, and none on an event with no equipment", async () => {
    signInAs(MOCK_ACCOUNTS.otherOrganiser)
    const withLines = await fetchEventRequest(WITH_EQUIPMENT)
    signInAs(MOCK_ACCOUNTS.organiser)

    const withoutLines = await fetchEventRequest(COORDINATORS_AWAITING_ANSWER)

    expect(withLines.equipment_lines.map((line) => line.quantity)).toEqual([8, 4])
    expect(withoutLines.equipment_lines).toEqual([])
  })
})
