import {
  changeHoldExpiry,
  decideBookingRequest,
  fetchBookingRequests,
  fetchPendingBookingRequests,
  placeBookingHold,
  raiseBookingRequest,
  withdrawArrangement,
} from '@/features/booking/api'
import { fetchVenueCalendar } from '@/features/venues/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { refusal, signInAs, signInAsNewAttendee, staffAccount } from './backend'
import { approvedEvent, EVENT_DATE, LEAD, newVenue, required, VENUE_STAFF } from './plannedEvent'

/**
 * SCRUM-75: Venue Staff hold a venue tentatively, move the hold's expiry and give final approval,
 * against the running backend (docs/adr/0045 decisions 13 to 18, docs/adr/0082).
 *
 * The refusals by role need only the staff account (an Event Coordinator) and new attendees. A
 * request to hold needs an approved event with venue requests, which takes a Lead and Venue
 * Staff, so those checks skip without INTEGRATION_LEAD_* and INTEGRATION_VENUE_STAFF_*.
 */

/** An id no database has, so the lookup finds nothing. */
const UNKNOWN_REQUEST_ID = 99_999_999
const canHold = LEAD !== null && VENUE_STAFF !== null
/** The events made here start at 09:00 on EVENT_DATE; these expiries are just before it. */
const EXPIRY = `${EVENT_DATE}T08:00:00+08:00`
const LATER_EXPIRY = `${EVENT_DATE}T08:30:00+08:00`
const HOLD_CALLS = {
  'placing a hold': () => placeBookingHold(UNKNOWN_REQUEST_ID, { expires_at: EXPIRY }),
  'changing an expiry': () => changeHoldExpiry(UNKNOWN_REQUEST_ID, { expires_at: EXPIRY }),
}

/**
 * An approved event, as the staff account (its coordinator), with one venue request at a new
 * venue for each purpose, in the morning; answers the event and the requests' ids in order.
 */
async function eventWithRequests(...purposes: string[]) {
  const event = await approvedEvent()
  const requestIds: number[] = []
  for (const purpose of purposes) {
    const venueId = await newVenue()
    await signInAs(staffAccount())
    const raised = await raiseBookingRequest(event.reference, {
      venue_id: venueId,
      starts_at: `${EVENT_DATE}T09:00:00+08:00`,
      ends_at: `${EVENT_DATE}T12:00:00+08:00`,
      purpose,
    })
    requestIds.push(raised.id)
  }
  await signInAs(required(VENUE_STAFF))
  return { reference: event.reference, requestIds }
}

afterEach(() => sendRequestsAs(null))

describe('SCRUM-75 tentative holds against the backend: who may hold', () => {
  it.each(Object.entries(HOLD_CALLS))('refuses %s without a token (401)', async (_name, call) => {
    expect(await refusal(call())).toMatchObject({ status: 401, code: 'authentication_error' })
  })

  it.each(Object.entries(HOLD_CALLS))(
    'refuses %s to an Event Coordinator and an Attendee (403)',
    async (_name, call) => {
      await signInAs(staffAccount())
      const coordinator = await refusal(call())
      await signInAsNewAttendee()
      const attendee = await refusal(call())

      expect([coordinator, attendee]).toMatchObject([
        { status: 403, code: 'authorization_error' },
        { status: 403, code: 'authorization_error' },
      ])
    },
  )

  it.skipIf(VENUE_STAFF === null).each(Object.entries(HOLD_CALLS))(
    'answers %s on a request that does not exist with 404',
    async (_name, call) => {
      await signInAs(required(VENUE_STAFF))

      expect(await refusal(call())).toMatchObject({
        status: 404,
        code: 'not_found',
        message: 'Booking request not found.',
      })
    },
  )
})

describe('SCRUM-75 tentative holds against the backend: a hold from start to finish', () => {
  it.skipIf(!canHold)(
    "refuses a hold on an event's only venue request (409), whatever the expiry",
    async () => {
      const { requestIds } = await eventWithRequests('Only hall')
      const [onlyHall = 0] = requestIds

      expect(await refusal(placeBookingHold(onlyHall, { expires_at: EXPIRY }))).toMatchObject({
        status: 409,
        code: 'conflict',
        message: 'A hold can only be placed on a request of an event with more than one venue.',
      })
    },
  )

  it.skipIf(!canHold)(
    'names the expiry it refuses (400): one that has passed, and one at the event start',
    async () => {
      const { requestIds } = await eventWithRequests('Main hall', 'Breakout room')
      const [mainHall = 0] = requestIds

      const passed = await refusal(
        placeBookingHold(mainHall, { expires_at: '2020-01-01T09:00:00+08:00' }),
      )
      const atStart = await refusal(
        placeBookingHold(mainHall, { expires_at: `${EVENT_DATE}T09:00:00+08:00` }),
      )

      expect(passed).toMatchObject({ status: 400, code: 'validation_error' })
      expect(passed.fieldErrors).toEqual({ expires_at: ['The expiry must be in the future.'] })
      expect(atStart.fieldErrors).toEqual({
        expires_at: ['The expiry must be before the event starts.'],
      })
    },
  )

  it.skipIf(!canHold)(
    'holds a request, lists it with its expiry for Venue Staff and the coordinator, moves the expiry, then approves it',
    async () => {
      const { reference, requestIds } = await eventWithRequests('Main hall', 'Breakout room')
      const [mainHall = 0, breakoutRoom = 0] = requestIds

      // --- Placed: On Hold with the expiry, in the business time zone (AC1, AC3) ---
      const held = await placeBookingHold(mainHall, { expires_at: EXPIRY })
      expect(held).toMatchObject({ id: mainHall, status: 'on_hold', hold_expires_at: EXPIRY })
      const queue = await fetchPendingBookingRequests()
      expect(queue.find((waiting) => waiting.id === mainHall)).toMatchObject({
        status: 'on_hold',
        hold_expires_at: EXPIRY,
      })
      expect(await refusal(placeBookingHold(mainHall, { expires_at: LATER_EXPIRY }))).toMatchObject(
        {
          status: 409,
          message: 'Only a pending or conflicting request can be held; this one is on_hold.',
        },
      )

      // --- Moved (AC4), and the coordinator sees the hold and its expiry (AC9) ---
      const moved = await changeHoldExpiry(mainHall, { expires_at: LATER_EXPIRY })
      expect(moved).toMatchObject({ status: 'on_hold', hold_expires_at: LATER_EXPIRY })
      await signInAs(staffAccount())
      const coordinatorsView = await fetchBookingRequests(reference)
      expect(coordinatorsView.map((request) => [request.status, request.hold_expires_at])).toEqual([
        ['on_hold', LATER_EXPIRY],
        ['pending', null],
      ])
      expect(coordinatorsView[1]?.id).toBe(breakoutRoom)

      // --- Final approval books it, and there is no expiry left to move (AC7, AC8) ---
      await signInAs(required(VENUE_STAFF))
      const approved = await decideBookingRequest(mainHall, { outcome: 'approved' })
      expect(approved).toMatchObject({ status: 'approved', hold_expires_at: null })
      expect(await refusal(changeHoldExpiry(mainHall, { expires_at: LATER_EXPIRY }))).toMatchObject(
        {
          status: 409,
          code: 'conflict',
          message: 'Only a request on hold has an expiry to change; this one is approved.',
        },
      )
    },
  )
})

describe('SCRUM-93 withdrawing a held request against the backend', () => {
  /** The whole of EVENT_DATE, as the calendar route reads a range (business time). */
  const EVENT_DAY = { range_start: `${EVENT_DATE}T00:00`, range_end: `${EVENT_DATE}T23:59` }

  it.skipIf(!canHold)(
    'releases its hold: the venue is free again, Venue Staff no longer wait on it, and the other request stays',
    async () => {
      const { reference, requestIds } = await eventWithRequests('Main hall', 'Breakout room')
      const [mainHall = 0, breakoutRoom = 0] = requestIds
      const held = await placeBookingHold(mainHall, { expires_at: EXPIRY })
      const calendarWhileHeld = await fetchVenueCalendar(held.venue_id, EVENT_DAY)

      await signInAs(staffAccount())
      const withdrawn = await withdrawArrangement(reference, mainHall)

      expect(calendarWhileHeld.map((entry) => entry.kind)).toEqual(['tentative_hold'])
      expect(withdrawn).toMatchObject({ id: mainHall, status: 'withdrawn', hold_expires_at: null })
      const listed = await fetchBookingRequests(reference)
      expect(listed.map((request) => [request.id, request.status])).toEqual([
        [mainHall, 'withdrawn'],
        [breakoutRoom, 'pending'],
      ])
      await signInAs(required(VENUE_STAFF))
      expect(await fetchVenueCalendar(held.venue_id, EVENT_DAY)).toEqual([])
      const queue = await fetchPendingBookingRequests()
      expect(queue.map((waiting) => waiting.id)).not.toContain(mainHall)
    },
  )
})
