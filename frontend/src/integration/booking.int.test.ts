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
import { confirmEvent, fetchEventRequestsWithVenueBookings } from '@/features/eventRequests/api'
import { ApiError } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { signInAs, staffAccount, uniqueEmail, VALID_PASSWORD } from './backend'
import {
  approvedEvent,
  coordinatorPosts,
  EVENT_DATE,
  eventReadyForSafetyReview,
  LEAD,
  newVenue,
  SAFETY_OFFICER,
  safetyApprovedEvent,
  VENUE_STAFF,
} from './plannedEvent'

/** A well-formed reference no database has, so the lookup finds nothing. */
const UNKNOWN_EVENT_REFERENCE = 'EVR-NOSUCH00'
const NOT_FOUND_MESSAGE = 'Event request not found.'
/** A cancel-all body: the reason goes on each approved booking it cancels (ADR-0118). */
const CANCEL_ALL = { reason: 'The conference moved online.' }

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

  it('names a replacement id that is not a whole number from 1 (400, SCRUM-92)', async () => {
    await signInAsCoordinator()

    const error = await refusal(
      raiseBookingRequest(UNKNOWN_EVENT_REFERENCE, {
        venue_id: 1,
        starts_at: '2026-11-10T09:00:00+08:00',
        ends_at: '2026-11-10T12:00:00+08:00',
        purpose: 'Keynote',
        replaces_request_id: 0,
      }),
    )

    expect(error).toMatchObject({ status: 400, code: 'validation_error' })
    expect(error.fieldErrors).toEqual({
      replaces_request_id: ['replaces_request_id must be a positive number.'],
    })
  })

  it.todo('raises a request for an approved event and lists it (needs a seeded approved event)')
  it.todo('refuses a second Pending request for the same venue and period (409)')
  // A replacement for a flagged arrangement (SCRUM-92) is raised in planning.int.test.ts, whose
  // events reach an approved venue.
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
      expect(typeof waiting.flagged_after_change).toBe('boolean')
      expect(Array.isArray(waiting.reassessment_flags)).toBe(true)
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
    'cancel all': () => cancelAllArrangements(UNKNOWN_EVENT_REFERENCE, CANCEL_ALL),
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
})

describe('SCRUM-93 AC10 venue arrangements change only while the event is planned, against the backend', () => {
  /** Rejecting an event needs a venue request on it, so a Lead and Venue Staff. */
  const canReject = LEAD !== null && VENUE_STAFF !== null
  /** Confirming an event needs the Safety Officer's approval too. */
  const canConfirm = canReject && SAFETY_OFFICER !== null

  /** An id no database has: the event's status is checked before the arrangement is looked for. */
  const UNKNOWN_ARRANGEMENT_ID = 99_999_999

  function notInPlanning(status: string): string {
    return `Only an approved event or one in Safety Review can have its venue arrangements withdrawn, changed or cancelled; this one is ${status}.`
  }

  /**
   * Withdraw, change and cancel all, one after another, on an arrangement of `reference`, as
   * whoever is signed in; answers how the backend refused each.
   */
  async function refusalsOfEachAction(reference: string, arrangementId: number) {
    const calls = [
      () => withdrawArrangement(reference, arrangementId),
      () => changeArrangement(reference, arrangementId, { purpose: 'Opening plenary' }),
      () => cancelAllArrangements(reference, CANCEL_ALL),
    ]
    const refusals = []
    for (const call of calls) {
      const error = await refusal(call())
      refusals.push({ status: error.status, code: error.code, message: error.message })
    }
    return refusals
  }

  it.skipIf(!canConfirm)(
    'lets them through in Safety Review, then refuses all three once the event is Confirmed, naming its status',
    async () => {
      const { reference, bookingId } = await safetyApprovedEvent()
      await signInAs(staffAccount())

      // --- In Safety Review the event is still being planned: the approved booking itself refuses ---
      expect((await refusal(withdrawArrangement(reference, bookingId))).message).toBe(
        'Only a pending, conflicting, held, rejected or expired arrangement can be withdrawn; this one is approved.',
      )

      // --- Confirmed: refused for the event's status, before the arrangement is looked at ---
      await confirmEvent(reference)
      const refused = { status: 409, code: 'conflict', message: notInPlanning('confirmed') }
      expect(await refusalsOfEachAction(reference, bookingId)).toEqual([refused, refused, refused])
      expect(await refusal(withdrawArrangement(reference, UNKNOWN_ARRANGEMENT_ID))).toMatchObject(
        refused,
      )
      const [booking] = await fetchBookingRequests(reference)
      expect(booking).toMatchObject({ id: bookingId, status: 'approved' })
    },
  )

  it.skipIf(!canReject)('refuses all three on a Rejected event, naming its status', async () => {
    const { reference } = await approvedEvent()
    const venueId = await newVenue()
    await signInAs(staffAccount())
    const raised = await raiseBookingRequest(reference, {
      venue_id: venueId,
      starts_at: `${EVENT_DATE}T09:00:00+08:00`,
      ends_at: `${EVENT_DATE}T12:00:00+08:00`,
      purpose: 'Main hall',
    })
    await coordinatorPosts(reference, 'reject', { reason: 'The venue fell through.' })

    const refused = { status: 409, code: 'conflict', message: notInPlanning('rejected') }
    expect(await refusalsOfEachAction(reference, raised.id)).toEqual([refused, refused, refused])
  })
})

describe('SCRUM-93 AC6 cancelling all of an event’s arrangements, approved bookings included, against the backend', () => {
  /** An approved booking needs Venue Staff, and the event a Lead. */
  const canBook = LEAD !== null && VENUE_STAFF !== null

  it.skipIf(!canBook)(
    'needs a reason, then cancels the approved booking and withdraws the pending request',
    async () => {
      const { reference, bookingId } = await eventReadyForSafetyReview()
      const venueId = await newVenue()
      await signInAs(staffAccount())
      const pending = await raiseBookingRequest(reference, {
        venue_id: venueId,
        starts_at: `${EVENT_DATE}T13:00:00+08:00`,
        ends_at: `${EVENT_DATE}T16:00:00+08:00`,
        purpose: 'Breakout room',
      })

      // --- No reason: refused, and nothing changes ---
      const noReason = await refusal(cancelAllArrangements(reference, {}))
      expect(noReason).toMatchObject({ status: 400, code: 'validation_error' })
      expect(noReason.fieldErrors).toEqual({
        reason: ['A reason is required to cancel a booking.'],
      })

      // --- With one: the booking is cancelled and the request withdrawn, in period order ---
      const retired = await cancelAllArrangements(reference, CANCEL_ALL)
      expect(retired.map((arrangement) => [arrangement.id, arrangement.status])).toEqual([
        [bookingId, 'cancelled'],
        [pending.id, 'withdrawn'],
      ])
    },
  )
})

describe("SCRUM-24 Venue Staff's list of events against the backend", () => {
  /** The backend's EVENT_LIST_FIELDS, in alphabetical order. */
  const EVENT_LIST_ROW_FIELDS = [
    'end_date',
    'end_time',
    'name',
    'proposed_date',
    'reference',
    'start_time',
    'status',
  ]

  it('refuses the list without a token (401)', async () => {
    const error = await refusal(fetchEventRequestsWithVenueBookings())

    expect(error).toMatchObject({ status: 401, code: 'authentication_error' })
  })

  it.each([
    ['an Attendee', signInAsAttendee],
    ['an Event Coordinator', signInAsCoordinator],
  ])('refuses the list to %s (403)', async (_role, signIn) => {
    await signIn()

    const error = await refusal(fetchEventRequestsWithVenueBookings())

    expect(error).toMatchObject({ status: 403, code: 'authorization_error' })
  })

  it.skipIf(!hasVenueStaff)(
    'answers Venue Staff with summary rows, or says there are none',
    async () => {
      await signInAsVenueStaff()

      const body = await fetchEventRequestsWithVenueBookings()

      // Other files may have raised requests on this backend, so the list may or may not be empty.
      if (body.event_requests.length === 0) {
        expect(body.message).toBe('No events have a venue booking request yet.')
      } else {
        expect(body.message).toBeUndefined()
      }
      for (const row of body.event_requests) {
        expect(Object.keys(row).sort()).toEqual(EVENT_LIST_ROW_FIELDS)
      }
    },
  )

  // Which events are listed is checked with the Venue Staff events screen and its API function.
  it.todo('lists an event with an active booking request and leaves a withdrawn one out')
})
