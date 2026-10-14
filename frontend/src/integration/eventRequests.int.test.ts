import { ROLE } from '@/config/roles'
import { logIn, register } from '@/features/auth/api'
import { fetchMyEventRequests } from '@/features/eventRequests/api'
import { apiRequest } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { staffAccount, uniqueEmail, VALID_PASSWORD } from './backend'
import type { Credentials } from './backend'

/**
 * GET /api/events/requests against the running backend (SCRUM-7, SCRUM-20 AC4, SCRUM-24 AC10).
 * Each test records its own client organisation, which only staff may do (SCRUM-66), so these
 * tests sign in as the staff account INTEGRATION_STAFF_EMAIL / INTEGRATION_STAFF_PASSWORD.
 */

const NO_REQUESTS_MESSAGE = 'Your organisation has no event requests yet.'
const NOT_PERMITTED_MESSAGE = 'You do not have permission to perform this action.'

/** Every field the frontend's EventRequest type reads, and nothing more (no internal ids). */
const EVENT_REQUEST_FIELDS = [
  'accessibility_needs',
  'created_at',
  'description',
  'end_date',
  'end_time',
  'equipment_requirements',
  'expected_attendance',
  'name',
  'proposed_date',
  'purpose',
  'reference',
  'registration_required',
  'start_time',
  'status',
  'venue_requirements',
]

/** A date a month from now, as the backend reads dates: never in the past. */
const EVENT_DATE = new Date(Date.now() + 30 * 24 * 60 * 60_000).toISOString().slice(0, 10)

const SUBMITTED = {
  name: 'Integration Summit',
  proposed_date: EVENT_DATE,
  end_date: EVENT_DATE,
  start_time: '09:00',
  end_time: '17:00',
  expected_attendance: 120,
}

/** Log in, and send that user's token with every request from now on. */
async function signInAs(credentials: Credentials): Promise<void> {
  const session = await logIn(credentials)
  sendRequestsAs(session.access_token)
}

/** A client organisation recorded by staff, under a name no earlier run has used. */
async function newOrganisation(): Promise<number> {
  await signInAs(staffAccount())
  const organisation = await apiRequest<{ id: number }>('/api/organisations', {
    method: 'POST',
    body: {
      name: `Integration organisation ${uniqueEmail('organisation')}`,
      contact_name: 'Integration Contact',
      contact_email: uniqueEmail('contact'),
    },
  })
  return organisation.id
}

/** A user who signed up, ready to log in. */
async function newAccount(label: string, organisationId: number | null): Promise<Credentials> {
  const credentials = { email: uniqueEmail(label), password: VALID_PASSWORD }
  await register({
    full_name: `Integration ${label}`,
    ...credentials,
    role: organisationId === null ? ROLE.ATTENDEE : ROLE.EVENT_ORGANISER,
    organisation_id: organisationId,
  })
  return credentials
}

/** As the signed-in organiser: submit a request, then save a draft. Returns their references. */
async function submitThenDraft(): Promise<{ submitted: string; draft: string }> {
  const submitted = await apiRequest<{ reference: string }>('/api/events/requests', {
    method: 'POST',
    body: SUBMITTED,
  })
  const draft = await apiRequest<{ reference: string }>('/api/events/requests/drafts', {
    method: 'POST',
    body: { name: 'Integration Draft' },
  })
  return { submitted: submitted.reference, draft: draft.reference }
}

afterEach(() => sendRequestsAs(null))

describe('SCRUM-7 organiser event list against the backend', () => {
  it('gives a new organisation an empty list and the message saying so', async () => {
    const organiser = await newAccount('organiser', await newOrganisation())
    await signInAs(organiser)

    expect(await fetchMyEventRequests()).toEqual({
      event_requests: [],
      message: NO_REQUESTS_MESSAGE,
    })
  })

  it('lists requests newest first, in exactly the shape the frontend reads', async () => {
    const organiser = await newAccount('organiser', await newOrganisation())
    await signInAs(organiser)
    const references = await submitThenDraft()

    const list = await fetchMyEventRequests()

    expect(list).not.toHaveProperty('message')
    expect(list.event_requests.map((row) => row.reference)).toEqual([
      references.draft,
      references.submitted,
    ])
    const [draft, submitted] = list.event_requests
    expect(draft).toMatchObject({
      status: 'draft',
      name: 'Integration Draft',
      proposed_date: null,
      start_time: null,
      end_time: null,
      expected_attendance: null,
    })
    expect(submitted).toMatchObject({
      status: 'submitted',
      name: SUBMITTED.name,
      proposed_date: EVENT_DATE,
      end_date: EVENT_DATE,
      start_time: '09:00:00',
      end_time: '17:00:00',
      expected_attendance: 120,
      registration_required: false,
    })
    for (const row of list.event_requests) {
      expect(Object.keys(row).sort()).toEqual(EVENT_REQUEST_FIELDS)
    }
  })

  it("shows a colleague the organisation's request but not the organiser's draft", async () => {
    const organisationId = await newOrganisation()
    const organiser = await newAccount('organiser', organisationId)
    const colleague = await newAccount('colleague', organisationId)
    await signInAs(organiser)
    const references = await submitThenDraft()

    await signInAs(colleague)
    const list = await fetchMyEventRequests()

    expect(list.event_requests.map((row) => row.reference)).toEqual([references.submitted])
  })

  it('refuses anyone who is not an Event Organiser', async () => {
    await signInAs(await newAccount('attendee', null))

    await expect(fetchMyEventRequests()).rejects.toMatchObject({
      status: 403,
      code: 'authorization_error',
      message: NOT_PERMITTED_MESSAGE,
    })
  })
})
