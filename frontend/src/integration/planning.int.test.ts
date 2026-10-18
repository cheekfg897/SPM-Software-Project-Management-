import { ROLE } from '@/config/roles'
import { register } from '@/features/auth/api'
import { decideBookingRequest, raiseBookingRequest } from '@/features/booking/api'
import {
  completeEvent,
  decideEventRequest,
  fetchEventRequest,
  sendToSafetyReview,
  startEventRequestReview,
  submitEventRequest,
} from '@/features/eventRequests/api'
import { assignCoordinator } from '@/features/lead/api'
import { apiRequest } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { refusal, signInAs, staffAccount, uniqueEmail, VALID_PASSWORD } from './backend'
import type { Credentials } from './backend'

/**
 * The coordinator's planning actions against the running backend: sending an event to safety
 * review (SCRUM-97, ADR-0047) and marking it completed (SCRUM-68, ADR-0027) (ADR-0075).
 *
 * The refusals that need no event of the coordinator's run with the staff account every run has
 * (an Event Coordinator) and new organisers. An event of the coordinator's needs a Lead to assign
 * it, and an approved venue needs Venue Staff, so those checks read the accounts from
 * INTEGRATION_LEAD_* and INTEGRATION_VENUE_STAFF_* and skip without them. CI makes them on the
 * SCRUM-98 branch (frontend.yml).
 */

const NOT_PERMITTED = {
  status: 403,
  code: 'authorization_error',
  message: 'You do not have permission to perform this action.',
}
const NOT_SIGNED_IN = { status: 401, code: 'authentication_error' }
const NOT_FOUND = { status: 404, code: 'not_found', message: 'Event request not found.' }
/** Every field of the event request the actions answer with (EventRequestSchema). */
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
const SAFETY_REVIEW_NOT_READY = {
  status: 409,
  code: 'safety_review_not_allowed',
  message:
    'The event can go to Safety Review once every venue arrangement is approved and every ' +
    'equipment request has an outcome from Technical Support.',
}

/** A staff account read from two variables, or null when either is unset. */
function optionalAccount(email: string | undefined, password: string | undefined) {
  if (email === undefined || email === '' || password === undefined || password === '') {
    return null
  }
  return { email, password }
}

const LEAD = optionalAccount(
  import.meta.env.INTEGRATION_LEAD_EMAIL,
  import.meta.env.INTEGRATION_LEAD_PASSWORD,
)
const VENUE_STAFF = optionalAccount(
  import.meta.env.INTEGRATION_VENUE_STAFF_EMAIL,
  import.meta.env.INTEGRATION_VENUE_STAFF_PASSWORD,
)
const canAssign = LEAD !== null
const canApproveVenue = canAssign && VENUE_STAFF !== null

/** The account, which the test's skip condition has already checked is set. */
function required(account: Credentials | null): Credentials {
  if (account === null) {
    throw new Error('This check needs an account that is not set; it should have been skipped.')
  }
  return account
}

/** A date `days` from now, as the backend reads dates ("2026-11-20"). */
function daysFromNow(days: number): string {
  return new Date(Date.now() + days * 24 * 60 * 60_000).toISOString().slice(0, 10)
}

const EVENT_DATE = daysFromNow(30)

/** As the staff account: record a client organisation and sign its organiser up. */
async function newOrganiser(): Promise<Credentials> {
  await signInAs(staffAccount())
  const organisation = await apiRequest<{ id: number }>('/api/organisations', {
    method: 'POST',
    body: {
      name: `Integration organisation ${uniqueEmail('organisation')}`,
      contact_name: 'Integration Contact',
      contact_email: uniqueEmail('contact'),
    },
  })
  const organiser = { email: uniqueEmail('organiser'), password: VALID_PASSWORD }
  await register({
    full_name: 'Integration Organiser',
    ...organiser,
    role: ROLE.EVENT_ORGANISER,
    organisation_id: organisation.id,
  })
  return organiser
}

/** A new organiser's submitted request, with no coordinator yet. Leaves the organiser signed in. */
async function submittedEvent(): Promise<string> {
  await signInAs(await newOrganiser())
  const submitted = await submitEventRequest({
    name: 'Integration Planning',
    proposed_date: EVENT_DATE,
    end_date: EVENT_DATE,
    start_time: '09:00',
    end_time: '17:00',
    expected_attendance: 120,
  })
  return submitted.reference
}

/** A submitted request the Lead has assigned to the staff account, signed in as it. */
async function assignedEvent(): Promise<string> {
  const reference = await submittedEvent()
  await signInAs(required(LEAD))
  await assignCoordinator({ reference, coordinator_email: staffAccount().email })
  await signInAs(staffAccount())
  return reference
}

/** An event the staff account has approved, with nothing arranged yet, signed in as it. */
async function approvedEvent(): Promise<string> {
  const reference = await assignedEvent()
  await startEventRequestReview(reference)
  await decideEventRequest(reference, { outcome: 'approved' })
  return reference
}

/** As Venue Staff: a new venue, big enough for every event here. */
async function newVenue(): Promise<number> {
  await signInAs(required(VENUE_STAFF))
  const venue = await apiRequest<{ id: number }>('/api/venues', {
    method: 'POST',
    body: {
      name: `Integration Hall ${uniqueEmail('venue')}`,
      location: 'Level 1',
      capacity: 300,
      supported_layouts: ['theatre'],
      facilities: ['projector'],
      accessibility_features: ['wheelchair_access'],
    },
  })
  return venue.id
}

/** As the staff account: ask for a new venue for the morning of the event. Returns its id. */
async function raiseVenueRequest(reference: string): Promise<number> {
  const venueId = await newVenue()
  await signInAs(staffAccount())
  const booking = await raiseBookingRequest(reference, {
    venue_id: venueId,
    starts_at: `${EVENT_DATE}T09:00:00+08:00`,
    ends_at: `${EVENT_DATE}T12:00:00+08:00`,
    purpose: 'Integration planning',
  })
  return booking.id
}

/** An approved event whose one venue Venue Staff approved: ready for safety review. */
async function settledEvent(): Promise<string> {
  const reference = await approvedEvent()
  const bookingId = await raiseVenueRequest(reference)
  await signInAs(required(VENUE_STAFF))
  await decideBookingRequest(bookingId, { outcome: 'approved' })
  await signInAs(staffAccount())
  return reference
}

afterEach(() => sendRequestsAs(null))

describe('SCRUM-97 sending an event to safety review against the backend', () => {
  it('refuses an organiser by role, and a visitor without a token', async () => {
    const reference = await submittedEvent()

    expect(await refusal(sendToSafetyReview(reference))).toMatchObject(NOT_PERMITTED)
    sendRequestsAs(null)
    expect(await refusal(sendToSafetyReview(reference))).toMatchObject(NOT_SIGNED_IN)
  })

  it('answers a coordinator an event not assigned to them as not found', async () => {
    const reference = await submittedEvent()
    await signInAs(staffAccount())

    expect(await refusal(sendToSafetyReview(reference))).toMatchObject(NOT_FOUND)
  })

  it.skipIf(!canAssign)('refuses an event not yet approved, with no gaps', async () => {
    const reference = await assignedEvent()

    const error = await refusal(sendToSafetyReview(reference))

    expect(error).toMatchObject({
      status: 409,
      code: 'safety_review_not_allowed',
      message: 'Only an approved event can go to Safety Review.',
    })
    expect(error.fieldErrors).toEqual({})
  })

  it.skipIf(!canAssign)('names a missing venue on an approved event with none', async () => {
    const reference = await approvedEvent()

    const error = await refusal(sendToSafetyReview(reference))

    expect(error).toMatchObject(SAFETY_REVIEW_NOT_READY)
    expect(error.fieldErrors).toEqual({ venue_arrangements: ['The event has no venue arranged.'] })
  })

  it.skipIf(!canApproveVenue)(
    'names a pending venue arrangement by its id and status',
    async () => {
      const reference = await approvedEvent()
      const bookingId = await raiseVenueRequest(reference)

      const error = await refusal(sendToSafetyReview(reference))

      expect(error).toMatchObject(SAFETY_REVIEW_NOT_READY)
      expect(error.fieldErrors).toEqual({
        venue_arrangements: [`Venue arrangement ${bookingId} is pending.`],
      })
    },
  )

  it.skipIf(!canApproveVenue)(
    'sends a settled event, answering in the shape the page reads',
    async () => {
      const reference = await settledEvent()

      const sent = await sendToSafetyReview(reference)

      expect(Object.keys(sent).sort()).toEqual(EVENT_REQUEST_FIELDS)
      expect(sent).toMatchObject({ reference, status: 'safety_review' })
      expect((await fetchEventRequest(reference)).status).toBe('safety_review')
    },
  )
})

describe('SCRUM-68 marking an event completed against the backend', () => {
  it('refuses an organiser by role, and a visitor without a token', async () => {
    const reference = await submittedEvent()

    expect(await refusal(completeEvent(reference))).toMatchObject(NOT_PERMITTED)
    sendRequestsAs(null)
    expect(await refusal(completeEvent(reference))).toMatchObject(NOT_SIGNED_IN)
  })

  it('answers a coordinator an event not assigned to them as not found', async () => {
    const reference = await submittedEvent()
    await signInAs(staffAccount())

    expect(await refusal(completeEvent(reference))).toMatchObject(NOT_FOUND)
  })

  it.skipIf(!canAssign)('refuses an event that is not confirmed', async () => {
    const reference = await approvedEvent()

    expect(await refusal(completeEvent(reference))).toMatchObject({
      status: 409,
      code: 'request_not_completable',
      message: 'Only a confirmed event can be marked completed.',
    })
  })
})
