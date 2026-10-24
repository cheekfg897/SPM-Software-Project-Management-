import {
  fetchActiveEvents,
  fetchCoordinatorWorkload,
  fetchUnassignedQueue,
  reassignCoordinator,
} from '@/features/lead/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { refusal, signInAs, signInAsNewAttendee, staffAccount } from './backend'
import { LEAD, required, submittedEvent } from './plannedEvent'

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
 * Lead's own answers need a Lead account and events held by coordinators, which only
 * `flask create-staff-user` and a coordinator's work can make, so those wait as todos and the mock
 * handlers in src/mocks/handlers/lead.ts stand in (docs/adr/0062).
 */
describe('SCRUM-96 Lead oversight contract (ADR-0041)', () => {
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

  it.todo(
    'lists every active event newest first, each with exactly the list fields, its status and its coordinator by name (null when nobody holds it)',
  )
  it.todo(
    'lists each coordinator holding an active event, ordered by name, with exactly the list fields of those events',
  )
  it.todo('answers an empty active list and an empty workload with their messages')
  it.todo(
    'reassigns by coordinator_email and answers the request with the new coordinator, including the fields the mock omits',
  )
  it.todo(
    'refuses a reassignment in order: payload 400, reference 404, no coordinator 409, not active 409, unknown email 400, same coordinator 409',
  )
})
