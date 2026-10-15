import { ROLE } from '@/config/roles'
import { register } from '@/features/auth/api'
import {
  fetchEventRequest,
  fetchMyEventRequests,
  saveDraftEventRequest,
  submitDraftEventRequest,
  submitEventRequest,
  updateDraftEventRequest,
} from '@/features/eventRequests/api'
import { apiRequest } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { signInAs, staffAccount, uniqueEmail, VALID_PASSWORD } from './backend'
import type { Credentials } from './backend'

/**
 * The organiser's event requests against the running backend: the list (SCRUM-7, SCRUM-20 AC4,
 * SCRUM-24 AC10), submitting one (SCRUM-19), and saving, changing and submitting a draft
 * (SCRUM-20, ADR-0024).
 * Each test records its own client organisation, which only staff may do (SCRUM-66), so these
 * tests sign in as the staff account INTEGRATION_STAFF_EMAIL / INTEGRATION_STAFF_PASSWORD.
 */

const NO_REQUESTS_MESSAGE = 'Your organisation has no event requests yet.'
const NOT_PERMITTED_MESSAGE = 'You do not have permission to perform this action.'
const MISSING_MESSAGE = 'Missing data for required field.'
const NOT_A_DRAFT_MESSAGE = 'Only a draft event request can be changed or submitted this way.'

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

/** A date `days` from now, as the backend reads dates ("2026-11-20"). */
function daysFromNow(days: number): string {
  return new Date(Date.now() + days * 24 * 60 * 60_000).toISOString().slice(0, 10)
}

/** A month from now: never in the past. */
const EVENT_DATE = daysFromNow(30)

const SUBMITTED = {
  name: 'Integration Summit',
  proposed_date: EVENT_DATE,
  end_date: EVENT_DATE,
  start_time: '09:00',
  end_time: '17:00',
  expected_attendance: 120,
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

/** Sign in as a new organiser of a new organisation, and return the organisation. */
async function signInAsNewOrganiser(): Promise<number> {
  const organisationId = await newOrganisation()
  await signInAs(await newAccount('organiser', organisationId))
  return organisationId
}

describe('SCRUM-19 submitting a request against the backend', () => {
  it('submits, ending the day it starts, in exactly the shape the frontend reads', async () => {
    await signInAsNewOrganiser()

    const submitted = await submitEventRequest({
      name: SUBMITTED.name,
      proposed_date: EVENT_DATE,
      start_time: '09:00',
      end_time: '17:00',
      expected_attendance: 120,
      registration_required: true,
    })

    expect(submitted).toMatchObject({
      status: 'submitted',
      proposed_date: EVENT_DATE,
      end_date: EVENT_DATE,
      start_time: '09:00:00',
      end_time: '17:00:00',
      registration_required: true,
    })
    expect(submitted.reference).toMatch(/^EVR-[A-Z0-9]{8}$/)
    expect(Object.keys(submitted).sort()).toEqual(EVENT_REQUEST_FIELDS)
  })

  it('names every required field left out', async () => {
    await signInAsNewOrganiser()

    await expect(submitEventRequest({ name: 'Only a name' })).rejects.toMatchObject({
      status: 400,
      code: 'validation_error',
      fieldErrors: {
        proposed_date: [MISSING_MESSAGE],
        start_time: [MISSING_MESSAGE],
        end_time: [MISSING_MESSAGE],
        expected_attendance: [MISSING_MESSAGE],
      },
    })
  })

  it.each([
    [
      { proposed_date: daysFromNow(-3) },
      { proposed_date: ['Proposed date cannot be in the past.'] },
    ],
    [{ end_time: '08:00' }, { end_time: ['Event must end after it starts.'] }],
    [{ end_date: daysFromNow(29) }, { end_date: ['End date cannot be before the proposed date.'] }],
    [
      { expected_attendance: 0 },
      { expected_attendance: ['Expected attendance must be at least 1.'] },
    ],
    [{ name: '   ' }, { name: ['Event name must not be blank.'] }],
  ])('refuses %j with the message the form shows', async (change, fieldErrors) => {
    await signInAsNewOrganiser()

    await expect(submitEventRequest({ ...SUBMITTED, ...change })).rejects.toMatchObject({
      status: 400,
      code: 'validation_error',
      fieldErrors,
    })
  })
})

describe('SCRUM-20 drafts against the backend', () => {
  it('saves a draft with only a name, its other fields empty, in the shape the frontend reads', async () => {
    await signInAsNewOrganiser()

    const draft = await saveDraftEventRequest({ name: 'Integration Draft' })

    expect(draft).toMatchObject({ status: 'draft', proposed_date: null, end_date: null })
    expect(Object.keys(draft).sort()).toEqual(EVENT_REQUEST_FIELDS)
  })

  it('changes only the fields sent on a draft, and empties one sent as null', async () => {
    await signInAsNewOrganiser()
    const draft = await saveDraftEventRequest({ name: 'Integration Draft' })
    await updateDraftEventRequest(draft.reference, { purpose: 'Planning' })

    const changed = await updateDraftEventRequest(draft.reference, {
      name: 'Renamed Draft',
      purpose: null,
    })

    expect(changed).toMatchObject({ name: 'Renamed Draft', purpose: null })
    expect(await fetchEventRequest(draft.reference)).toMatchObject({
      reference: draft.reference,
      name: 'Renamed Draft',
      purpose: null,
    })
  })

  it('refuses to submit a draft missing details, then submits it once they are saved', async () => {
    await signInAsNewOrganiser()
    const draft = await saveDraftEventRequest({ name: 'Integration Draft' })

    await expect(submitDraftEventRequest(draft.reference)).rejects.toMatchObject({
      status: 400,
      fieldErrors: { proposed_date: [MISSING_MESSAGE], expected_attendance: [MISSING_MESSAGE] },
    })
    await updateDraftEventRequest(draft.reference, SUBMITTED)

    await expect(submitDraftEventRequest(draft.reference)).resolves.toMatchObject({
      reference: draft.reference,
      status: 'submitted',
    })
  })

  it('refuses a submitted request as not a draft, and a colleague draft as not found', async () => {
    const organisationId = await signInAsNewOrganiser()
    const submitted = await submitEventRequest(SUBMITTED)
    await signInAs(await newAccount('colleague', organisationId))
    const colleaguesDraft = await saveDraftEventRequest({ name: 'Colleague Draft' })

    await expect(
      updateDraftEventRequest(submitted.reference, { name: 'Mine' }),
    ).rejects.toMatchObject({
      status: 409,
      code: 'request_not_draft',
      message: NOT_A_DRAFT_MESSAGE,
    })
    await signInAs(await newAccount('organiser', organisationId))
    await expect(
      updateDraftEventRequest(colleaguesDraft.reference, { name: 'Mine' }),
    ).rejects.toMatchObject({ status: 404, code: 'not_found' })
  })

  it('opens one of the organisation requests with every field the frontend reads', async () => {
    await signInAsNewOrganiser()
    const draft = await saveDraftEventRequest({ name: 'Integration Draft' })

    const opened = await fetchEventRequest(draft.reference)

    expect(opened).toMatchObject({ reference: draft.reference, status: 'draft' })
    for (const field of EVENT_REQUEST_FIELDS) {
      expect(opened).toHaveProperty(field)
    }
  })
})
