import {
  assignCoordinator,
  fetchActiveEvents,
  fetchCoordinatorWorkload,
  fetchUnassignedQueue,
  reassignCoordinator,
} from '@/features/lead/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { refusal, signInAs, signInAsNewAttendee, staffAccount } from './backend'
import { LEAD, required, submittedEvent } from './plannedEvent'
import type { PlannedEvent } from './plannedEvent'

/** The fields the oversight lists send for an event (SCRUM-24 AC8), sorted. */
const LIST_FIELDS = [
  'end_date',
  'end_time',
  'name',
  'proposed_date',
  'reference',
  'start_time',
  'status',
]

/** The keys of `row`, sorted, or none when the row is missing. */
function keysOf(row: object | undefined): string[] {
  return row === undefined ? [] : Object.keys(row).sort()
}

/** As the Lead, give a new submitted event to the staff account. Leaves the Lead signed in. */
async function eventHeldByTheStaffAccount(): Promise<PlannedEvent> {
  const event = await submittedEvent()
  await signInAs(required(LEAD))
  await assignCoordinator({ reference: event.reference, coordinator_email: staffAccount().email })
  return event
}

/**
 * SCRUM-95: the Lead's queue against the real backend. Staff accounts can only be made with
 * `flask create-staff-user` (ADR-0023). The queue's rows are checked when the run has a Lead
 * account (INTEGRATION_LEAD_*, which CI makes); the other checks wait here as todos, and the mock
 * handlers in src/mocks/handlers/lead.ts stand in for the backend.
 */
describe('SCRUM-95 Lead queue contract (ADR-0036)', () => {
  afterEach(() => sendRequestsAs(null))

  it.skipIf(LEAD === null)(
    'lists each queued request with exactly its reference, the six AC2 fields and its status (SCRUM-24 AC8)',
    async () => {
      const event = await submittedEvent()
      await signInAs(required(LEAD))

      const { event_requests: rows } = await fetchUnassignedQueue()

      const row = rows.find((queued) => queued.reference === event.reference)
      expect(row === undefined ? [] : Object.keys(row).sort()).toEqual([
        'end_time',
        'expected_attendance',
        'name',
        'proposed_date',
        'reference',
        'start_time',
        'status',
        'submitted_at',
      ])
      expect(row).toMatchObject({ name: event.name, status: 'submitted', expected_attendance: 120 })
    },
  )
  it.todo('answers an empty queue with an empty list and the "waiting to be assigned" message')
  it.todo('refuses the queue to an Event Coordinator (403) and to a visitor (401)')
  it.todo(
    'assigns by coordinator_email and answers the request with its coordinator, including the full-schema fields the mock omits (status, the dates and so on)',
  )
  it.todo('takes an assigned request out of the queue')
  it.todo('answers 404 for an unknown reference and 409 for one that already has a coordinator')
  it.todo('answers 400 on coordinator_email for an unknown or non-coordinator email, checked last')
})

/**
 * SCRUM-96: the Lead's oversight routes against the real backend. The integration setup makes an
 * Event Coordinator (staffAccount) and can sign attendees up, so the refusals run for real. The
 * Lead's own answers run when the run has a Lead account (INTEGRATION_LEAD_*, which CI makes).
 * What a shared backend can't show (the order of every event, empty lists, a second coordinator to
 * reassign to) waits as todos, and the mock handlers in src/mocks/handlers/lead.ts stand in
 * (docs/adr/0062, docs/adr/0120).
 */
describe('SCRUM-96 Lead oversight contract (ADR-0041, ADR-0120)', () => {
  afterEach(() => sendRequestsAs(null))

  const OVERSIGHT_CALLS = {
    'the active list': () => fetchActiveEvents(),
    'the workload': () => fetchCoordinatorWorkload(),
    'a reassignment': () =>
      reassignCoordinator({
        reference: 'EVR-NOSUCH00',
        coordinator_email: 'nobody@example.com',
      }),
  }

  it.each(Object.entries(OVERSIGHT_CALLS))(
    'refuses an Event Coordinator %s with 403, before looking anything up (AC4)',
    async (_, call) => {
      await signInAs(staffAccount())

      const error = await refusal(call())

      expect(error.status).toBe(403)
      expect(error.code).toBe('authorization_error')
    },
  )

  it.each(Object.entries(OVERSIGHT_CALLS))('refuses an Attendee %s with 403', async (_, call) => {
    await signInAsNewAttendee()

    expect((await refusal(call())).status).toBe(403)
  })

  it.each(Object.entries(OVERSIGHT_CALLS))('refuses a visitor %s with 401', async (_, call) => {
    sendRequestsAs(null)

    expect((await refusal(call())).status).toBe(401)
  })

  it.skipIf(LEAD === null)(
    'lists a held event with exactly the list fields and its coordinator by name, and leaves out one nobody holds (ADR-0120)',
    async () => {
      const waiting = await submittedEvent()
      const held = await eventHeldByTheStaffAccount()

      const { event_requests: rows } = await fetchActiveEvents()

      expect(rows.map((row) => row.reference)).not.toContain(waiting.reference)
      const row = rows.find((active) => active.reference === held.reference)
      expect(keysOf(row)).toEqual(['coordinator', ...LIST_FIELDS])
      expect(row).toMatchObject({
        name: held.name,
        status: 'submitted',
        coordinator: expect.any(String) as string,
      })
    },
  )
  it.skipIf(LEAD === null)('lists the active events newest first', async () => {
    const older = await eventHeldByTheStaffAccount()
    const newer = await eventHeldByTheStaffAccount()

    const { event_requests: rows } = await fetchActiveEvents()

    const references = rows.map((row) => row.reference)
    expect(references.indexOf(newer.reference)).toBeGreaterThanOrEqual(0)
    expect(references.indexOf(newer.reference)).toBeLessThan(references.indexOf(older.reference))
  })
  it.skipIf(LEAD === null)(
    'lists each Event Coordinator with their count and exactly the list fields of their events (ADR-0120)',
    async () => {
      const held = await eventHeldByTheStaffAccount()

      const { coordinators } = await fetchCoordinatorWorkload()

      const names = coordinators.map((entry) => entry.coordinator)
      expect(names).toEqual([...names].sort())
      for (const entry of coordinators) {
        expect(keysOf(entry)).toEqual(['active_count', 'coordinator', 'event_requests'])
        expect(entry.active_count).toBe(entry.event_requests.length)
      }
      const holder = coordinators.find((entry) =>
        entry.event_requests.some((row) => row.reference === held.reference),
      )
      const row = holder?.event_requests.find((listed) => listed.reference === held.reference)
      expect(keysOf(row)).toEqual(LIST_FIELDS)
      expect(row).toMatchObject({ name: held.name, status: 'submitted' })
    },
  )
  it.todo(
    'lists an Event Coordinator who holds no active event with 0 (the run has no coordinator account it can keep idle)',
  )
  it.todo('answers an empty active list and an empty workload with their messages')
  it.todo(
    'reassigns by coordinator_email and answers the request with the new coordinator, including the fields the mock omits',
  )
  it.todo(
    'refuses a reassignment in order: payload 400, reference 404, no coordinator 409, not active 409, unknown email 400, same coordinator 409',
  )
})
