import { ROLE, STAFF_RECORD_READER_ROLES } from '@/config/roles'
import type { Role } from '@/config/roles'
import { updateBookingPreparation } from '@/features/booking/api'
import { reserveEquipment, updateReservationPreparation } from '@/features/equipment/api'
import {
  editEventRequest,
  fetchEventHistory,
  fetchStaffEventRecord,
} from '@/features/eventRequests/api'
import { reassignCoordinator } from '@/features/lead/api'
import { recordSafetyOutcome } from '@/features/safety/api'
import type { SafetyChecklist } from '@/features/safety/api'
import { refusal } from '@/test/refusal'

import { MOCK_ACCOUNTS } from '../fixtures/accounts'
import type { MockAccount } from '../fixtures/accounts'

import { NOT_FOUND, NOT_PERMITTED, NOT_SIGNED_IN, signInAs } from './test/eventRequestCalls'

/**
 * The mock of any submitted event's read-only staff record
 * (GET /api/events/requests/<reference>/staff-record), pinned to what the backend sends Venue
 * Staff, Technical Support, the Safety Officer and the Event Coordinator Lead (SCRUM-24 AC9,
 * AC10; SCRUM-84 AC2, SCRUM-85 AC2; ADR-0095). Each section comes from the mock that keeps it,
 * so a change made through another mock shows on the record. The integration tests check the
 * same route against the running backend.
 */

/** Chloe's event under review, with a programme note: the event-request mock's full record. */
const UNDER_REVIEW = 'EVR-7K2M9QXA'
/** Chloe's approved event with two equipment lines, safety-approved, so it can be prepared. */
const WITH_EQUIPMENT = 'EVR-MOCK0001'
/** The booking mock's safety-approved event, whose ballroom Venue Staff are preparing. */
const BEING_PREPARED = 'EVR-BOOK0110'
/** The booking mock's event with two rejected arrangements and a withdrawn one. */
const MULTI_VENUE = 'EVR-BOOK0106'
/** The Safety Officer's gala, waiting for its check. */
const GALA = 'EVR-SAFE0002'
/** The Lead's event held by Chloe, which only the Lead's mock knows. */
const LEADS_EVENT = 'EVR-LEAD0003'
/** An event only Technical Support's mock knows. */
const EQUIPMENT_ONLY = 'EVR-TECH0001'
const COLLEAGUES_DRAFT = 'EVR-H2PL8R6K'
/** A note on each checklist item, as the Safety Officer sends them. */
const CHECKLIST_NOTES: SafetyChecklist = {
  attendance_vs_capacity: '400 expected in a ballroom for 500.',
  venue_layout: 'Banquet layout.',
  emergency_access: 'Two exits, both signed.',
  accessibility: 'Wheelchair seating near the doors.',
  equipment_placement: 'Projectors ceiling-mounted.',
  crowd_movement: 'Staggered arrival.',
  venue_restrictions: 'No open flames.',
}

/** One mock account for each role, in ROLE's order, so a role added later is checked too. */
function accountsWithRoles(roles: readonly Role[]): [Role, MockAccount][] {
  const accounts: [Role, MockAccount][] = []
  for (const role of roles) {
    const account = Object.values(MOCK_ACCOUNTS).find((candidate) => candidate.role === role)
    if (account === undefined) {
      throw new Error(`No mock account has the role ${role}`)
    }
    accounts.push([role, account])
  }
  return accounts
}

const REFUSED_ROLES = Object.values(ROLE).filter(
  (role) => !STAFF_RECORD_READER_ROLES.includes(role),
)

describe('SCRUM-24 mock of the read-only staff record', () => {
  it('lets in exactly the four reader roles, and refuses the other three', () => {
    expect([...STAFF_RECORD_READER_ROLES].sort()).toEqual([
      ROLE.EVENT_COORDINATOR_LEAD,
      ROLE.SAFETY_OFFICER,
      ROLE.TECHNICAL_SUPPORT_STAFF,
      ROLE.VENUE_STAFF,
    ])
    expect([...REFUSED_ROLES].sort()).toEqual([
      ROLE.ATTENDEE,
      ROLE.EVENT_COORDINATOR,
      ROLE.EVENT_ORGANISER,
    ])
  })

  it.each(accountsWithRoles(STAFF_RECORD_READER_ROLES))(
    'opens an event its reader is not assigned to, as %s',
    async (_role, account) => {
      signInAs(account)

      const record = await fetchStaffEventRecord(UNDER_REVIEW)

      expect(record).toMatchObject({
        reference: UNDER_REVIEW,
        name: 'Partner Summit',
        status: 'under_review',
        programme_notes: 'Keynote at 9:30, breakout rooms after lunch.',
        internal_planning_notes: null,
        coordinator: { full_name: 'Chloe Lim', email: 'chloe@connectsphere.test' },
        decision: null,
        clarifications: [],
        venue_arrangements: [],
        equipment_lines: [],
        equipment_reservations: [],
        safety_outcome: null,
      })
      expect(record).not.toHaveProperty('registrants')
    },
  )

  it.each(accountsWithRoles(REFUSED_ROLES))(
    'refuses %s, an assigned coordinator included',
    async (_role, account) => {
      signInAs(account)

      expect(await refusal(fetchStaffEventRecord(UNDER_REVIEW))).toMatchObject(NOT_PERMITTED)
    },
  )

  it('refuses a visitor who is not signed in', async () => {
    signInAs(null)

    expect(await refusal(fetchStaffEventRecord(UNDER_REVIEW))).toMatchObject(NOT_SIGNED_IN)
  })

  it.each([
    ['a draft', COLLEAGUES_DRAFT],
    ['an unknown reference', 'EVR-NOSUCH01'],
  ])('answers %s as not found', async (_case, reference) => {
    signInAs(MOCK_ACCOUNTS.lead)

    expect(await refusal(fetchStaffEventRecord(reference))).toMatchObject(NOT_FOUND)
  })

  it('shows the internal planning notes the coordinator saved', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)
    await editEventRequest(UNDER_REVIEW, { internal_planning_notes: 'Client prefers mornings.' })
    signInAs(MOCK_ACCOUNTS.venueStaff)

    const record = await fetchStaffEventRecord(UNDER_REVIEW)

    expect(record.internal_planning_notes).toBe('Client prefers mornings.')
  })

  it('shows the active venue arrangements with their preparation, and not retired ones', async () => {
    signInAs(MOCK_ACCOUNTS.lead)

    const multiVenue = await fetchStaffEventRecord(MULTI_VENUE)
    const prepared = await fetchStaffEventRecord(BEING_PREPARED)

    expect(multiVenue.venue_arrangements.map((arrangement) => arrangement.status)).toEqual([
      'rejected',
      'rejected',
    ])
    expect(prepared.venue_arrangements).toEqual([
      {
        venue_name: 'Marina Hall',
        starts_at: '2026-11-12T09:00:00+08:00',
        ends_at: '2026-11-12T17:00:00+08:00',
        status: 'approved',
        preparation_status: 'in_progress',
        preparation_notes: 'Stage half built.',
      },
    ])
  })

  it('shows the preparation Venue Staff record afterwards', async () => {
    signInAs(MOCK_ACCOUNTS.venueStaff)
    await updateBookingPreparation(9109, { status: 'ready', notes: 'Stage built.' })
    signInAs(MOCK_ACCOUNTS.safetyOfficer)

    const [arrangement] = (await fetchStaffEventRecord(BEING_PREPARED)).venue_arrangements

    expect(arrangement).toMatchObject({
      preparation_status: 'ready',
      preparation_notes: 'Stage built.',
    })
  })

  it('shows the equipment by name with its outcome, and the reservations with their preparation', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)
    const reservation = await reserveEquipment(WITH_EQUIPMENT, {
      equipment_type_id: 2,
      quantity: 4,
    })
    await updateReservationPreparation(reservation.id, {
      status: 'in_progress',
      notes: 'Charging.',
    })
    // A decoy on another event, which this event's record must leave out.
    await reserveEquipment('EVR-APPROVED', { equipment_type_id: 1, quantity: 1 })
    signInAs(MOCK_ACCOUNTS.venueStaff)

    const record = await fetchStaffEventRecord(WITH_EQUIPMENT)

    expect(record.equipment_lines).toEqual([
      {
        equipment_type_name: 'Projector',
        quantity: 8,
        notes: 'Ceiling-mounted, with HDMI at the lectern.',
        status: 'requested',
        provided_quantity: null,
        outcome_note: null,
      },
      {
        equipment_type_name: 'Microphone',
        quantity: 4,
        notes: null,
        status: 'fulfilled',
        provided_quantity: 4,
        outcome_note: null,
      },
    ])
    expect(record.equipment_reservations).toEqual([
      {
        equipment_type_name: 'Microphone',
        quantity: 4,
        starts_at: reservation.starts_at,
        ends_at: reservation.ends_at,
        reserved_by: 'Tariq Hassan',
        preparation_status: 'in_progress',
        preparation_notes: 'Charging.',
      },
    ])
  })

  it('shows the outcome the Safety Officer records, with the checklist', async () => {
    signInAs(MOCK_ACCOUNTS.lead)
    expect((await fetchStaffEventRecord(GALA)).safety_outcome).toBeNull()
    signInAs(MOCK_ACCOUNTS.safetyOfficer)
    await recordSafetyOutcome({ reference: GALA, outcome: 'approved', checklist: CHECKLIST_NOTES })
    signInAs(MOCK_ACCOUNTS.lead)

    const record = await fetchStaffEventRecord(GALA)

    expect(record.safety_outcome).toEqual({
      outcome: 'approved',
      checklist: CHECKLIST_NOTES,
      reason: null,
      recorded_by: 'Sana Iyer',
      recorded_at: '2026-10-05T12:00:00+08:00',
    })
    expect(record.venue_arrangements.map((arrangement) => arrangement.venue_name)).toEqual([
      'Marina Ballroom',
    ])
    expect(record.equipment_lines.map((line) => line.equipment_type_name)).toEqual([
      'Projector',
      'Wireless microphone',
    ])
  })

  it('names the coordinator the Lead holds the event with now', async () => {
    signInAs(MOCK_ACCOUNTS.lead)
    expect((await fetchStaffEventRecord(LEADS_EVENT)).coordinator?.full_name).toBe('Chloe Lim')
    await reassignCoordinator({
      reference: LEADS_EVENT,
      coordinator_email: MOCK_ACCOUNTS.otherCoordinator.email,
    })

    const record = await fetchStaffEventRecord(LEADS_EVENT)

    expect(record.coordinator).toEqual({
      full_name: 'Aisha Karim',
      email: 'aisha@connectsphere.test',
    })
  })
})

describe('SCRUM-33 AC5 mock of the history on the staff record', () => {
  /** Events only another feature's mock holds: the booking, Lead's, Safety and equipment mocks. */
  const HELD_ELSEWHERE = [BEING_PREPARED, LEADS_EVENT, GALA, EQUIPMENT_ONLY]

  it.each(accountsWithRoles(STAFF_RECORD_READER_ROLES))(
    'answers the history of every event the record opens elsewhere, as %s',
    async (_role, account) => {
      signInAs(account)

      for (const reference of HELD_ELSEWHERE) {
        await fetchStaffEventRecord(reference)
        expect(await fetchEventHistory(reference)).toEqual({ history: [] })
      }
    },
  )

  it('still answers a coordinator not holding the event, and a draft, as not found', async () => {
    // Chloe holds the Lead's event, so Aisha may not read its history (SCRUM-24 AC10).
    signInAs(MOCK_ACCOUNTS.otherCoordinator)
    expect(await refusal(fetchEventHistory(LEADS_EVENT))).toMatchObject(NOT_FOUND)

    signInAs(MOCK_ACCOUNTS.lead)
    expect(await refusal(fetchEventHistory(COLLEAGUES_DRAFT))).toMatchObject(NOT_FOUND)
  })
})
