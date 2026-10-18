import { fetchCurrentUser, register } from '@/features/auth/api'
import {
  editEventRequest,
  fetchEventHistory,
  fetchRegistrants,
  submitEventRequest,
} from '@/features/eventRequests/api'
import { assignCoordinator } from '@/features/lead/api'
import { createOrganisation } from '@/features/organisations/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import {
  newOrganiser,
  refusal,
  signInAs,
  signInAsNewAttendee,
  staffAccount,
  uniqueEmail,
} from './backend'
import type { Credentials } from './backend'

/**
 * The sections of an event's record read from routes of their own, against the running
 * backend: its history (SCRUM-33 AC4, AC5; ADR-0025) and who registered (SCRUM-55), ADR-0076;
 * and the coordinator's edit, which the history records (SCRUM-33 AC1 to AC4, ADR-0079).
 * A registrant's own shape can't be checked here: registering needs a confirmed event with
 * registration open, which takes a Safety Officer, Venue Staff and Technical Support account.
 *
 * Only the Event Coordinator Lead assigns a coordinator (SCRUM-95), and Lead accounts are made
 * with `flask create-staff-user` like the staff account, so the checks that need an event
 * assigned to the staff account read a Lead from these variables and skip without them:
 * INTEGRATION_LEAD_EMAIL=... INTEGRATION_LEAD_PASSWORD=... npm run test:integration
 * They leave events assigned to the staff account, and SCRUM-24's check that a coordinator with
 * nothing assigned gets an empty list (eventRequests.int.test.ts) needs a staff account with
 * none: so with a Lead set, give each run a fresh staff account, as CI does.
 */

const LEAD_EMAIL = import.meta.env.INTEGRATION_LEAD_EMAIL ?? ''
const LEAD_PASSWORD = import.meta.env.INTEGRATION_LEAD_PASSWORD ?? ''
const hasLead = LEAD_EMAIL !== '' && LEAD_PASSWORD !== ''

const NOT_FOUND = { status: 404, code: 'not_found', message: 'Event request not found.' }
const NOT_PERMITTED = { status: 403, code: 'authorization_error' }
/** An event's registrants before anyone registers or a capacity is set (SCRUM-69). */
const NOBODY_REGISTERED = { capacity: null, registered_count: 0, places_left: null, items: [] }

/** A date `days` from now, as the backend reads dates ("2026-11-20"). */
function daysFromNow(days: number): string {
  return new Date(Date.now() + days * 24 * 60 * 60_000).toISOString().slice(0, 10)
}

/** A month from now: never in the past. */
const EVENT_DATE = daysFromNow(30)
/** Two days ago: in the past wherever the backend's "today" is. */
const PAST_DATE = daysFromNow(-2)

/** An organiser of an organisation no other test uses. Staff record it (SCRUM-66). */
async function newOrganiserAccount(): Promise<Credentials> {
  await signInAs(staffAccount())
  const organisation = await createOrganisation({
    name: `Integration organisation ${uniqueEmail('organisation')}`,
    contact_name: 'Integration Contact',
    contact_email: uniqueEmail('contact'),
  })
  sendRequestsAs(null)
  const organiser = newOrganiser(organisation.id)
  await register(organiser)
  return { email: organiser.email, password: organiser.password }
}

/** A new organiser submits a request; returns them, signed in, and its reference. */
async function submittedByNewOrganiser() {
  const organiser = await newOrganiserAccount()
  await signInAs(organiser)
  const submitted = await submitEventRequest({
    name: 'Integration Record Sections',
    proposed_date: EVENT_DATE,
    start_time: '09:00',
    end_time: '17:00',
    expected_attendance: 60,
  })
  return { organiser, reference: submitted.reference }
}

/**
 * The Lead gives the request to the staff account, an Event Coordinator, who is signed in
 * after. Returns both their names, as the history shows them.
 */
async function assignToStaffCoordinator(reference: string) {
  await signInAs({ email: LEAD_EMAIL, password: LEAD_PASSWORD })
  const lead = await fetchCurrentUser()
  await assignCoordinator({ reference, coordinator_email: staffAccount().email })
  await signInAs(staffAccount())
  const coordinator = await fetchCurrentUser()
  return { leadName: lead.full_name, coordinatorName: coordinator.full_name }
}

afterEach(() => sendRequestsAs(null))

describe('SCRUM-33 AC5 an event history against the backend', () => {
  it('gives the organiser of a request nobody has worked on yet an empty history', async () => {
    const { reference } = await submittedByNewOrganiser()

    expect(await fetchEventHistory(reference)).toEqual({ history: [] })
  })

  it("answers another organisation's organiser, and a coordinator it isn't assigned to, as not found", async () => {
    const { reference } = await submittedByNewOrganiser()
    await signInAs(await newOrganiserAccount())
    const otherOrganiser = await refusal(fetchEventHistory(reference))
    await signInAs(staffAccount())
    const coordinator = await refusal(fetchEventHistory(reference))

    expect(otherOrganiser).toMatchObject(NOT_FOUND)
    expect(coordinator).toMatchObject(NOT_FOUND)
  })

  it('refuses an attendee', async () => {
    const { reference } = await submittedByNewOrganiser()
    await signInAsNewAttendee()

    expect(await refusal(fetchEventHistory(reference))).toMatchObject(NOT_PERMITTED)
  })

  it.skipIf(!hasLead)(
    'shows the assignment to its coordinator and its organiser in the shape the page reads',
    async () => {
      const { organiser, reference } = await submittedByNewOrganiser()
      const { leadName, coordinatorName } = await assignToStaffCoordinator(reference)

      const { history } = await fetchEventHistory(reference)
      await signInAs(organiser)
      const organisersCopy = await fetchEventHistory(reference)

      expect(history).toHaveLength(1)
      const [assigned] = history
      expect(assigned).toEqual({
        kind: 'coordinator_assigned',
        occurred_at: assigned?.occurred_at,
        actor_name: leadName,
        details: { coordinator_name: coordinatorName },
      })
      // Business time with its offset (ADR-0009), which the page formats.
      expect(assigned?.occurred_at).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.*\+08:00$/)
      expect(organisersCopy).toEqual({ history })
    },
  )
})

describe('SCRUM-55 an event registrants against the backend', () => {
  it('gives the organiser of a new request nobody and no capacity, in the shape the page reads (AC1, AC4)', async () => {
    const { reference } = await submittedByNewOrganiser()

    expect(await fetchRegistrants(reference)).toEqual(NOBODY_REGISTERED)
  })

  it("answers another organisation's organiser, and a coordinator it isn't assigned to, as not found", async () => {
    const { reference } = await submittedByNewOrganiser()
    await signInAs(await newOrganiserAccount())
    const otherOrganiser = await refusal(fetchRegistrants(reference))
    await signInAs(staffAccount())
    const coordinator = await refusal(fetchRegistrants(reference))

    expect(otherOrganiser).toMatchObject(NOT_FOUND)
    expect(coordinator).toMatchObject(NOT_FOUND)
  })

  it('refuses an attendee (AC5)', async () => {
    const { reference } = await submittedByNewOrganiser()
    await signInAsNewAttendee()

    expect(await refusal(fetchRegistrants(reference))).toMatchObject(NOT_PERMITTED)
  })

  it.skipIf(!hasLead)('gives the assigned coordinator the same list (AC2)', async () => {
    const { reference } = await submittedByNewOrganiser()
    await assignToStaffCoordinator(reference)

    expect(await fetchRegistrants(reference)).toEqual(NOBODY_REGISTERED)
  })
})

/** The request's history entries the edit wrote: every one but the assignment. */
async function editsInHistory(reference: string) {
  const { history } = await fetchEventHistory(reference)
  return history.filter((entry) => entry.kind === 'field_changed')
}

describe('SCRUM-33 AC1 to AC4 the coordinator edit against the backend', () => {
  it('refuses an organiser, even on their own request', async () => {
    const { reference } = await submittedByNewOrganiser()

    expect(await refusal(editEventRequest(reference, { description: 'x' }))).toMatchObject(
      NOT_PERMITTED,
    )
  })

  it("answers a coordinator a request that isn't theirs as not found", async () => {
    const { reference } = await submittedByNewOrganiser()
    await signInAs(staffAccount())

    expect(await refusal(editEventRequest(reference, { description: 'x' }))).toMatchObject(
      NOT_FOUND,
    )
  })

  it.skipIf(!hasLead)(
    'changes the fields sent, says which are significant, and records each in the history',
    async () => {
      const { reference } = await submittedByNewOrganiser()
      const { coordinatorName } = await assignToStaffCoordinator(reference)

      const edited = await editEventRequest(reference, {
        expected_attendance: 75,
        description: 'Now with a panel.',
      })

      expect(edited).toMatchObject({
        reference,
        description: 'Now with a panel.',
        expected_attendance: 75,
        programme_notes: null,
        internal_planning_notes: null,
      })
      const changes = [
        {
          field: 'description',
          previous_value: null,
          new_value: 'Now with a panel.',
          significant: false,
        },
        { field: 'expected_attendance', previous_value: 60, new_value: 75, significant: true },
      ]
      expect(edited.changes).toEqual(changes)
      const edits = await editsInHistory(reference)
      expect(edits.map((entry) => entry.details)).toEqual(changes)
      expect(edits.map((entry) => entry.actor_name)).toEqual([coordinatorName, coordinatorName])
    },
  )

  it.skipIf(!hasLead)('moves the end date with a date moved on its own', async () => {
    const { reference } = await submittedByNewOrganiser()
    await assignToStaffCoordinator(reference)
    const later = daysFromNow(37)

    const edited = await editEventRequest(reference, { proposed_date: later })

    expect(edited.end_date).toBe(later)
    expect(edited.changes.map((change) => [change.field, change.new_value])).toEqual([
      ['proposed_date', later],
      ['end_date', later],
    ])
  })

  it.skipIf(!hasLead)(
    'keeps the internal planning notes out of the organiser history (ADR-0025)',
    async () => {
      const { organiser, reference } = await submittedByNewOrganiser()
      await assignToStaffCoordinator(reference)

      const edited = await editEventRequest(reference, { internal_planning_notes: 'Call AV.' })
      const coordinatorsEdits = await editsInHistory(reference)
      await signInAs(organiser)
      const organisersEdits = await editsInHistory(reference)

      expect(edited.internal_planning_notes).toBe('Call AV.')
      expect(coordinatorsEdits).toHaveLength(1)
      expect(organisersEdits).toEqual([])
    },
  )

  it.skipIf(!hasLead).each<[Record<string, unknown>, string, string]>([
    [{ proposed_date: PAST_DATE }, 'proposed_date', 'Proposed date cannot be in the past.'],
    [{ expected_attendance: 0 }, 'expected_attendance', 'Expected attendance must be at least 1.'],
    [{ end_time: null }, 'end_time', 'Field may not be null.'],
    [{ name: 'Renamed' }, 'name', 'Unknown field.'],
    [{ end_time: '08:00' }, 'end_time', 'Event must end after it starts.'],
  ])('refuses %j with the message on %s', async (changes, field, message) => {
    const { reference } = await submittedByNewOrganiser()
    await assignToStaffCoordinator(reference)

    const error = await refusal(editEventRequest(reference, changes))

    expect(error).toMatchObject({
      status: 400,
      code: 'validation_error',
      fieldErrors: { [field]: [message] },
    })
  })
})
