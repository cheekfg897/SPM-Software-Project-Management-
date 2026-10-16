import {
  fetchEventRequest,
  fetchMyEventRequests,
  saveDraftEventRequest,
  submitDraftEventRequest,
  submitEventRequest,
  updateDraftEventRequest,
} from '@/features/eventRequests/api'
import type { EventRequestDetails } from '@/features/eventRequests/api'
import { refusal } from '@/test/refusal'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { MOCK_ACCOUNTS, mockTokenFor } from '../fixtures/accounts'
import type { MockAccount } from '../fixtures/accounts'

import { resetMockEventRequests } from './eventRequests'

/**
 * The mock of submitting an event request and saving, editing and submitting a draft
 * (SCRUM-19, SCRUM-20, ADR-0001 to ADR-0004, ADR-0024), pinned to the backend's own answers
 * and messages. The mock's "today" is Monday 2026-10-05. The integration tests check the same
 * contract against the running backend.
 */

const MISSING = 'Missing data for required field.'
const NOT_A_DRAFT = 'Only a draft event request can be changed or submitted this way.'

/** The organiser's own draft, a colleague's draft, and the organiser's request under review. */
const OWN_DRAFT = 'EVR-3HD8PL2W'
const COLLEAGUES_DRAFT = 'EVR-H2PL8R6K'
const UNDER_REVIEW = 'EVR-7K2M9QXA'
const OTHER_ORGANISATIONS = 'EVR-N5QS3V9C'

const COMPLETE: EventRequestDetails = {
  name: 'Harbour Lights Gala',
  purpose: 'Fundraiser',
  description: 'An evening on the water.',
  proposed_date: '2026-11-20',
  start_time: '19:00',
  end_time: '23:00',
  expected_attendance: 300,
  venue_requirements: 'Waterfront, standing room',
  accessibility_needs: 'Step-free access',
  equipment_requirements: 'Two microphones',
  registration_required: true,
}

function signInAs(account: MockAccount) {
  sendRequestsAs(mockTokenFor(account))
}

describe('SCRUM-19 mock: submitting a new request', () => {
  beforeEach(() => signInAs(MOCK_ACCOUNTS.organiser))

  it("submits a complete request, ending the day it starts, at the top of the organiser's list", async () => {
    const submitted = await submitEventRequest(COMPLETE)

    expect(submitted).toMatchObject({
      ...COMPLETE,
      status: 'submitted',
      start_time: '19:00:00',
      end_time: '23:00:00',
      end_date: '2026-11-20',
    })
    expect(submitted.reference).toMatch(/^EVR-[A-Z0-9]{8}$/)
    const list = await fetchMyEventRequests()
    expect(list.event_requests[0]?.reference).toBe(submitted.reference)
  })

  it('names every required field left out', async () => {
    const error = await refusal(submitEventRequest({ name: 'Just a name' }))

    expect(error).toMatchObject({
      status: 400,
      code: 'validation_error',
      fieldErrors: {
        proposed_date: [MISSING],
        start_time: [MISSING],
        end_time: [MISSING],
        expected_attendance: [MISSING],
      },
    })
  })

  it.each([
    [{ proposed_date: '2026-10-04' }, { proposed_date: ['Proposed date cannot be in the past.'] }],
    [{ end_time: '18:00' }, { end_time: ['Event must end after it starts.'] }],
    [{ end_date: '2026-11-19' }, { end_date: ['End date cannot be before the proposed date.'] }],
    [
      { expected_attendance: 0 },
      { expected_attendance: ['Expected attendance must be at least 1.'] },
    ],
    [{ name: '   ' }, { name: ['Event name must not be blank.'] }],
  ])('refuses %j with the message %j', async (change, fieldErrors) => {
    const error = await refusal(submitEventRequest({ ...COMPLETE, ...change }))

    expect(error).toMatchObject({ status: 400, code: 'validation_error', fieldErrors })
  })

  it("accepts an event on today's date, which is not in the past", async () => {
    const submitted = await submitEventRequest({ ...COMPLETE, proposed_date: '2026-10-05' })

    expect(submitted.proposed_date).toBe('2026-10-05')
  })

  it('refuses an event that ends the moment it starts', async () => {
    const error = await refusal(submitEventRequest({ ...COMPLETE, end_time: '19:00' }))

    expect(error).toMatchObject({
      status: 400,
      fieldErrors: { end_time: ['Event must end after it starts.'] },
    })
  })

  it('accepts an event that runs past midnight into the next day', async () => {
    const submitted = await submitEventRequest({
      ...COMPLETE,
      end_date: '2026-11-21',
      end_time: '02:00',
    })

    expect(submitted).toMatchObject({ end_date: '2026-11-21', end_time: '02:00:00' })
  })

  it('forgets what was submitted when reset, so one test cannot leak into another', async () => {
    const submitted = await submitEventRequest(COMPLETE)
    resetMockEventRequests()

    const list = await fetchMyEventRequests()
    expect(list.event_requests.map((row) => row.reference)).not.toContain(submitted.reference)
  })
})

describe('SCRUM-20 mock: drafts', () => {
  beforeEach(() => signInAs(MOCK_ACCOUNTS.organiser))

  it('saves a draft with only its name, leaving the rest empty', async () => {
    const draft = await saveDraftEventRequest({ name: 'Spring Fair' })

    expect(draft).toMatchObject({
      name: 'Spring Fair',
      status: 'draft',
      proposed_date: null,
      end_date: null,
      registration_required: false,
    })
  })

  it('refuses a draft without a name', async () => {
    const error = await refusal(saveDraftEventRequest({ name: ' ' }))

    expect(error).toMatchObject({
      status: 400,
      fieldErrors: { name: ['Event name must not be blank.'] },
    })
  })

  it('keeps a date in the past on a draft until it is submitted', async () => {
    const draft = await saveDraftEventRequest({ name: 'Old idea', proposed_date: '2026-01-01' })

    expect(draft.proposed_date).toBe('2026-01-01')
  })

  it("changes only the fields sent on the organiser's own draft, and clears one sent as null", async () => {
    await updateDraftEventRequest(OWN_DRAFT, { purpose: 'Team offsite' })

    const changed = await updateDraftEventRequest(OWN_DRAFT, {
      name: 'Renamed draft',
      purpose: null,
    })

    expect(changed).toMatchObject({ reference: OWN_DRAFT, name: 'Renamed draft', purpose: null })
    expect((await fetchEventRequest(OWN_DRAFT)).name).toBe('Renamed draft')
  })

  it("answers a colleague's draft as not found, and a request under review as not a draft", async () => {
    const colleagues = await refusal(updateDraftEventRequest(COLLEAGUES_DRAFT, { name: 'Mine' }))
    const underReview = await refusal(updateDraftEventRequest(UNDER_REVIEW, { name: 'Mine' }))

    expect(colleagues).toMatchObject({ status: 404, code: 'not_found' })
    expect(underReview).toMatchObject({
      status: 409,
      code: 'request_not_draft',
      message: NOT_A_DRAFT,
    })
  })

  it('refuses to submit a draft until it has every required detail, then submits it', async () => {
    const draft = await saveDraftEventRequest({ name: 'Spring Fair' })

    const incomplete = await refusal(submitDraftEventRequest(draft.reference))
    await updateDraftEventRequest(draft.reference, { ...COMPLETE, name: 'Spring Fair' })
    const submitted = await submitDraftEventRequest(draft.reference)

    expect(incomplete).toMatchObject({
      status: 400,
      fieldErrors: { proposed_date: [MISSING], expected_attendance: [MISSING] },
    })
    expect(submitted).toMatchObject({ reference: draft.reference, status: 'submitted' })
  })

  it('refuses to submit a request that is no longer a draft', async () => {
    const error = await refusal(submitDraftEventRequest(UNDER_REVIEW))

    expect(error).toMatchObject({ status: 409, code: 'request_not_draft' })
  })
})

describe('SCRUM-20 mock: opening one request', () => {
  beforeEach(() => signInAs(MOCK_ACCOUNTS.organiser))

  it("opens a request of the organiser's organisation", async () => {
    const request = await fetchEventRequest(OWN_DRAFT)

    expect(request).toMatchObject({ reference: OWN_DRAFT, status: 'draft' })
  })

  it("answers another organisation's request as not found", async () => {
    const error = await refusal(fetchEventRequest(OTHER_ORGANISATIONS))

    expect(error).toMatchObject({ status: 404, code: 'not_found' })
  })
})

describe('SCRUM-19 mock: who may submit', () => {
  it('refuses a visitor who is not signed in', async () => {
    sendRequestsAs(null)

    await expect(submitEventRequest(COMPLETE)).rejects.toMatchObject({ status: 401 })
  })

  it('refuses anyone who is not an Event Organiser', async () => {
    signInAs(MOCK_ACCOUNTS.attendee)

    await expect(saveDraftEventRequest({ name: 'Mine' })).rejects.toMatchObject({
      status: 403,
      code: 'authorization_error',
    })
  })

  it('refuses an organiser whose account has no client organisation', async () => {
    signInAs(MOCK_ACCOUNTS.unlinkedOrganiser)

    await expect(submitEventRequest(COMPLETE)).rejects.toMatchObject({
      status: 403,
      code: 'organiser_without_organisation',
    })
  })
})
