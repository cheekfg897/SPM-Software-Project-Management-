import { fetchCurrentUser, register } from '@/features/auth/api'
import { fetchEventHistory, submitEventRequest } from '@/features/eventRequests/api'
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
 * backend: its history (SCRUM-33 AC4, AC5; ADR-0025, ADR-0076).
 *
 * Only the Event Coordinator Lead assigns a coordinator (SCRUM-95), and Lead accounts are made
 * with `flask create-staff-user` like the staff account, so the checks that need an event
 * assigned to the staff account read a Lead from these variables and skip without them:
 * INTEGRATION_LEAD_EMAIL=... INTEGRATION_LEAD_PASSWORD=... npm run test:integration
 */

const LEAD_EMAIL = import.meta.env.INTEGRATION_LEAD_EMAIL ?? ''
const LEAD_PASSWORD = import.meta.env.INTEGRATION_LEAD_PASSWORD ?? ''
const hasLead = LEAD_EMAIL !== '' && LEAD_PASSWORD !== ''

const NOT_FOUND = { status: 404, code: 'not_found', message: 'Event request not found.' }
const NOT_PERMITTED = { status: 403, code: 'authorization_error' }

/** A date a month from now, as the backend reads dates ("2026-11-20"): never in the past. */
const EVENT_DATE = new Date(Date.now() + 30 * 24 * 60 * 60_000).toISOString().slice(0, 10)

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
