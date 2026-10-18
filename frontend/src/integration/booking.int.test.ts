import { ROLE } from '@/config/roles'
import {
  cancelAllArrangements,
  changeArrangement,
  decideBookingRequest,
  fetchBookingRequests,
  fetchPendingBookingRequests,
  raiseBookingRequest,
  withdrawArrangement,
} from '@/features/booking/api'
import { logIn, register } from '@/features/auth/api'
import { ApiError } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { staffAccount, uniqueEmail, VALID_PASSWORD } from './backend'

/** A well-formed reference no database has, so the lookup finds nothing. */
const UNKNOWN_EVENT_REFERENCE = 'EVR-NOSUCH00'
const NOT_FOUND_MESSAGE = 'Event request not found.'

/**
 * Venue Staff are made the same way as the staff account (`flask create-staff-user`), but CI does
 * not seed one, so the checks that need one read it from these variables and skip without them:
 * INTEGRATION_VENUE_STAFF_EMAIL=... INTEGRATION_VENUE_STAFF_PASSWORD=... npm run test:integration
 */
const VENUE_STAFF_EMAIL = import.meta.env.INTEGRATION_VENUE_STAFF_EMAIL
const VENUE_STAFF_PASSWORD = import.meta.env.INTEGRATION_VENUE_STAFF_PASSWORD
const hasVenueStaff = Boolean(VENUE_STAFF_EMAIL) && Boolean(VENUE_STAFF_PASSWORD)

/** The ApiError a call was refused with. Fails the test if it succeeded or failed another way. */
async function refusal(call: Promise<unknown>): Promise<ApiError> {
  const error = await call.then(
    () => expect.fail('Expected the backend to refuse the request.'),
    (caught: unknown) => caught,
  )
  if (!(error instanceof ApiError)) {
    throw new Error(`Expected an ApiError, got ${String(error)}`)
  }
  return error
}

async function signInAsAttendee() {
  const credentials = { email: uniqueEmail('attendee'), password: VALID_PASSWORD }
  await register({ full_name: 'Integration Attendee', role: ROLE.ATTENDEE, ...credentials })
  const session = await logIn(credentials)
  sendRequestsAs(session.access_token)
}

/** Sign in as the staff account, which is an Event Coordinator (see staffAccount). */
async function signInAsCoordinator() {
  const session = await logIn(staffAccount())
  sendRequestsAs(session.access_token)
}

async function signInAsVenueStaff() {
  const session = await logIn({
    email: VENUE_STAFF_EMAIL ?? '',
    password: VENUE_STAFF_PASSWORD ?? '',
  })
  sendRequestsAs(session.access_token)
}

afterEach(() => sendRequestsAs(null))

describe('SCRUM-42 venue booking requests against the backend', () => {
  it('refuses listing without a token (401)', async () => {
    const error = await refusal(fetchBookingRequests(UNKNOWN_EVENT_REFERENCE))

    expect(error).toMatchObject({ status: 401, code: 'authentication_error' })
  })

  it('refuses a role other than the Event Coordinator (403)', async () => {
    await signInAsAttendee()

    const error = await refusal(fetchBookingRequests(UNKNOWN_EVENT_REFERENCE))

    expect(error).toMatchObject({ status: 403, code: 'authorization_error' })
  })

  it('answers 404 for an event the coordinator has none of', async () => {
    await signInAsCoordinator()

    const error = await refusal(fetchBookingRequests(UNKNOWN_EVENT_REFERENCE))

    expect(error).toMatchObject({ status: 404, code: 'not_found', message: NOT_FOUND_MESSAGE })
  })

  it('names each field it refuses (400), before looking for the event', async () => {
    await signInAsCoordinator()

    const error = await refusal(
      raiseBookingRequest(UNKNOWN_EVENT_REFERENCE, {
        venue_id: 1,
        starts_at: '2026-11-10T09:00:00+08:00',
        ends_at: '2026-11-10T12:00:00+08:00',
        purpose: 'Keynote',
        justification: '   ',
      }),
    )

    expect(error).toMatchObject({ status: 400, code: 'validation_error' })
    expect(Object.keys(error.fieldErrors)).toEqual(['justification'])
  })

  it.todo('raises a request for an approved event and lists it (needs a seeded approved event)')
  it.todo('refuses a second Pending request for the same venue and period (409)')
  it.todo(
    'raises a replacement linked to a flagged arrangement (SCRUM-92; needs a seeded blocked booking)',
  )
})

describe('SCRUM-43 venue booking decisions against the backend', () => {
  /** An id no database has, so the lookup finds nothing. */
  const UNKNOWN_REQUEST_ID = 99_999_999

  it('refuses the queue without a token (401)', async () => {
    const error = await refusal(fetchPendingBookingRequests())

    expect(error).toMatchObject({ status: 401, code: 'authentication_error' })
  })

  it('refuses a role other than Venue Staff (403)', async () => {
    await signInAsAttendee()

    const error = await refusal(fetchPendingBookingRequests())

    expect(error).toMatchObject({ status: 403, code: 'authorization_error' })
  })

  it('refuses a decision without a token (401)', async () => {
    const error = await refusal(decideBookingRequest(UNKNOWN_REQUEST_ID, { outcome: 'approved' }))

    expect(error).toMatchObject({ status: 401, code: 'authentication_error' })
  })

  it('refuses a coordinator deciding a request (403)', async () => {
    await signInAsCoordinator()

    const error = await refusal(decideBookingRequest(UNKNOWN_REQUEST_ID, { outcome: 'approved' }))

    expect(error).toMatchObject({ status: 403, code: 'authorization_error' })
  })

  it.skipIf(!hasVenueStaff)('answers the queue with a list Venue Staff can read', async () => {
    await signInAsVenueStaff()

    const queue = await fetchPendingBookingRequests()

    expect(Array.isArray(queue)).toBe(true)
    for (const waiting of queue) {
      expect(waiting.status).toBe('pending')
      expect(typeof waiting.event_proposed_date).toBe('string')
      expect(typeof waiting.needs_alternative_venue).toBe('boolean')
      expect(Array.isArray(waiting.unavailability)).toBe(true)
    }
  })

  it.skipIf(!hasVenueStaff)('answers 404 for a request that does not exist', async () => {
    await signInAsVenueStaff()

    const error = await refusal(decideBookingRequest(UNKNOWN_REQUEST_ID, { outcome: 'approved' }))

    expect(error).toMatchObject({
      status: 404,
      code: 'not_found',
      message: 'Booking request not found.',
    })
  })

  it.todo('approves a Pending request and books the venue (needs a seeded pending request)')
  it.todo('refuses a rejection with no reason (400 on `reason`)')
})

describe('SCRUM-93 changing, withdrawing and cancelling venue arrangements against the backend', () => {
  /** An id no database has, on an event no database has. */
  const UNKNOWN_ARRANGEMENT_ID = 99_999_999
  const CALLS = {
    change: () =>
      changeArrangement(UNKNOWN_EVENT_REFERENCE, UNKNOWN_ARRANGEMENT_ID, { purpose: 'Keynote' }),
    withdraw: () => withdrawArrangement(UNKNOWN_EVENT_REFERENCE, UNKNOWN_ARRANGEMENT_ID),
    'cancel all': () => cancelAllArrangements(UNKNOWN_EVENT_REFERENCE),
  }

  it.each(Object.entries(CALLS))('refuses %s without a token (401)', async (_name, call) => {
    const error = await refusal(call())

    expect(error).toMatchObject({ status: 401, code: 'authentication_error' })
  })

  it.each(Object.entries(CALLS))(
    'refuses %s from a role other than the Event Coordinator (403)',
    async (_name, call) => {
      await signInAsAttendee()

      const error = await refusal(call())

      expect(error).toMatchObject({ status: 403, code: 'authorization_error' })
    },
  )

  it.each(Object.entries(CALLS))(
    'answers %s with 404 for an event the coordinator has none of',
    async (_name, call) => {
      await signInAsCoordinator()

      const error = await refusal(call())

      expect(error).toMatchObject({ status: 404, code: 'not_found', message: NOT_FOUND_MESSAGE })
    },
  )

  it('names each field of a change it refuses (400), before looking for the event', async () => {
    await signInAsCoordinator()

    const error = await refusal(
      changeArrangement(UNKNOWN_EVENT_REFERENCE, UNKNOWN_ARRANGEMENT_ID, {
        purpose: '   ',
        expected_occupancy: 0,
      }),
    )

    expect(error).toMatchObject({ status: 400, code: 'validation_error' })
    expect(error.fieldErrors).toEqual({
      purpose: ['Must not be blank.'],
      expected_occupancy: ['expected_occupancy must be a positive number.'],
    })
  })

  it.todo(
    'changes a pending arrangement and lists it with the new values (needs a seeded approved event)',
  )
  it.todo(
    'withdraws a pending arrangement and leaves the event’s others untouched (needs a seeded approved event)',
  )
  it.todo(
    'refuses to withdraw an approved arrangement, naming its status (409; needs a decided request)',
  )
  it.todo(
    'refuses withdraw, change and cancel all once the event is Confirmed, naming its status (lands with SCRUM-93 AC10 on the backend)',
  )
})

describe("SCRUM-24 Venue Staff's list of events against the backend", () => {
  // GET /api/events/requests/with-venue-bookings exists (ADR-0085), but no screen calls it yet,
  // so there is no API function to check. These land with the Venue Staff events screen.
  it.todo('refuses the list without a token (401) and to a role other than Venue Staff (403)')
  it.todo(
    'lists an event with a booking request as name, date, times and status, or says there are none',
  )
})
