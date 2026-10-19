import { ROLE } from '@/config/roles'
import {
  changeHoldExpiry,
  decideBookingRequest,
  fetchPendingBookingRequests,
  placeBookingHold,
  raiseBookingRequest,
  withdrawArrangement,
} from '@/features/booking/api'
import { apiRequest } from '@/lib/api'
import { refusalOf } from '@/test/refusalOf'

import { MOCK_ACCOUNTS } from '../fixtures/accounts'

import { MOCK_BOOKING_EVENTS } from './bookingFixtures'
import { accountsOfEveryRoleBut, signInAs } from './test/eventRequestCalls'

/**
 * The booking mock's tentative holds (SCRUM-75, ADR-0045 decisions 13 to 18), pinned to what
 * backend/app/modules/venue/services.py answers, messages included. The mock's "now" is
 * MOCK_NOW (5 Oct 2026). Breakout room (9001) is one of two venues for its event, which starts
 * at 09:00 on 20 Nov; Main hall (9002) is its event's only venue.
 */

const BREAKOUT_ROOM = 9001
const MAIN_HALL = 9002
/** Already on hold when a test starts, for its own single-venue event (MOCK_ARRANGEMENTS). */
const HELD_STUDIO = 9108
const BEFORE_THE_WORKSHOP = '2026-11-15T17:00:00+08:00'
const LATER_BEFORE_THE_WORKSHOP = '2026-11-18T12:00:00+08:00'
/** Before the approved event, which starts at 09:00 on 10 Nov. */
const BEFORE_THE_KEYNOTE = '2026-11-01T17:00:00+08:00'
const HOLD_URL = (requestId: number) => `/api/venues/booking-requests/${requestId}/hold`

function hold(requestId: number, expiresAt = BEFORE_THE_WORKSHOP) {
  return placeBookingHold(requestId, { expires_at: expiresAt })
}

function statusIn(queue: { id: number; status: string }[], requestId: number) {
  return queue.find((waiting) => waiting.id === requestId)?.status
}

/** As the coordinator, raise a request for the Breakout room's venue at an overlapping time. */
async function raiseOverlappingRequest(): Promise<number> {
  signInAs(MOCK_ACCOUNTS.coordinator)
  const overlapping = await raiseBookingRequest(MOCK_BOOKING_EVENTS.approved.reference, {
    venue_id: 1,
    starts_at: '2026-11-20T11:00:00+08:00',
    ends_at: '2026-11-20T14:00:00+08:00',
    purpose: 'Overlapping talk',
  })
  signInAs(MOCK_ACCOUNTS.venueStaff)
  return overlapping.id
}

/**
 * As the coordinator, raise two requests for the approved event (10 Nov, 09:00) at different
 * venues, then sign back in as Venue Staff; answers their ids.
 */
async function raiseTwoVenues(): Promise<{ kept: number; other: number }> {
  signInAs(MOCK_ACCOUNTS.coordinator)
  const reference = MOCK_BOOKING_EVENTS.approved.reference
  const kept = await raiseBookingRequest(reference, {
    venue_id: 1,
    starts_at: '2026-11-10T09:00:00+08:00',
    ends_at: '2026-11-10T12:00:00+08:00',
    purpose: 'Keynote',
  })
  const other = await raiseBookingRequest(reference, {
    venue_id: 2,
    starts_at: '2026-11-10T13:00:00+08:00',
    ends_at: '2026-11-10T15:00:00+08:00',
    purpose: 'Workshop',
    expected_occupancy: 10,
  })
  signInAs(MOCK_ACCOUNTS.venueStaff)
  return { kept: kept.id, other: other.id }
}

beforeEach(() => signInAs(MOCK_ACCOUNTS.venueStaff))

describe('SCRUM-75 booking mock: placing a hold', () => {
  it('holds a request of a multi-venue event until the expiry, and keeps it in the queue', async () => {
    const held = await hold(BREAKOUT_ROOM)

    expect(held).toMatchObject({
      id: BREAKOUT_ROOM,
      status: 'on_hold',
      hold_expires_at: BEFORE_THE_WORKSHOP,
    })
    const queue = await fetchPendingBookingRequests()
    expect(queue.map((waiting) => [waiting.id, waiting.status, waiting.hold_expires_at])).toEqual([
      [BREAKOUT_ROOM, 'on_hold', BEFORE_THE_WORKSHOP],
      [HELD_STUDIO, 'on_hold', '2026-11-21T09:00:00+08:00'],
      [MAIN_HALL, 'pending', null],
    ])
  })

  it('refuses a hold on a request whose event has only that venue (409)', async () => {
    const error = await refusalOf(hold(MAIN_HALL))

    expect(error).toMatchObject({
      status: 409,
      code: 'conflict',
      message: 'A hold can only be placed on a request of an event with more than one venue.',
    })
  })

  it('counts only the venues the event still has: a withdrawn one does not make it multi-venue', async () => {
    const { kept, other } = await raiseTwoVenues()
    signInAs(MOCK_ACCOUNTS.coordinator)
    await withdrawArrangement(MOCK_BOOKING_EVENTS.approved.reference, other)
    signInAs(MOCK_ACCOUNTS.venueStaff)

    const error = await refusalOf(hold(kept, BEFORE_THE_KEYNOTE))

    expect(error.message).toBe(
      'A hold can only be placed on a request of an event with more than one venue.',
    )
  })

  it('still counts a rejected venue until the coordinator withdraws it, so the event stays multi-venue', async () => {
    const { kept, other } = await raiseTwoVenues()
    await decideBookingRequest(other, { outcome: 'rejected', reason: 'Hall closed' })

    const held = await hold(kept, BEFORE_THE_KEYNOTE)

    expect(held).toMatchObject({ id: kept, status: 'on_hold' })
  })

  it.each([
    ['is missing', undefined, 'Missing data for required field.'],
    ['is not a date-time', 'next Friday', 'Not a valid datetime.'],
    ['has passed', '2026-10-05T12:00:00+08:00', 'The expiry must be in the future.'],
    [
      'is when the event starts',
      '2026-11-20T09:00:00+08:00',
      'The expiry must be before the event starts.',
    ],
  ])('refuses an expiry that %s (400 on expires_at)', async (_case, expiresAt, message) => {
    const error = await refusalOf(
      apiRequest(HOLD_URL(BREAKOUT_ROOM), { method: 'POST', body: { expires_at: expiresAt } }),
    )

    expect(error).toMatchObject({
      status: 400,
      code: 'validation_error',
      message: 'Invalid request.',
    })
    expect(error.fieldErrors).toEqual({ expires_at: [message] })
  })

  it('refuses to hold a request that is already on hold, naming its status (409)', async () => {
    await hold(BREAKOUT_ROOM)

    const error = await refusalOf(hold(BREAKOUT_ROOM))

    expect(error).toMatchObject({
      status: 409,
      message: 'Only a pending or conflicting request can be held; this one is on_hold.',
    })
  })

  it('refuses a hold that clashes with a booking at the venue, as an approval is (409)', async () => {
    const overlapping = await raiseOverlappingRequest()
    await decideBookingRequest(overlapping, { outcome: 'approved' })

    const error = await refusalOf(hold(BREAKOUT_ROOM))

    expect(error).toMatchObject({
      status: 409,
      message: `Cannot approve: booking #${overlapping} already holds this venue during the requested period.`,
    })
  })

  it('makes a live hold block approving another request for the same venue and period', async () => {
    const overlapping = await raiseOverlappingRequest()
    await hold(BREAKOUT_ROOM)

    const error = await refusalOf(decideBookingRequest(overlapping, { outcome: 'approved' }))

    expect(error.message).toBe(
      `Cannot approve: booking #${BREAKOUT_ROOM} already holds this venue during the requested period.`,
    )
  })
})

describe('SCRUM-75 booking mock: changing a hold’s expiry', () => {
  it('moves the expiry of a request on hold', async () => {
    await hold(BREAKOUT_ROOM)

    const moved = await changeHoldExpiry(BREAKOUT_ROOM, { expires_at: LATER_BEFORE_THE_WORKSHOP })

    expect(moved).toMatchObject({ status: 'on_hold', hold_expires_at: LATER_BEFORE_THE_WORKSHOP })
  })

  it('refuses to move the expiry of a request that is not on hold, naming its status (409)', async () => {
    const error = await refusalOf(
      changeHoldExpiry(BREAKOUT_ROOM, { expires_at: LATER_BEFORE_THE_WORKSHOP }),
    )

    expect(error).toMatchObject({
      status: 409,
      code: 'conflict',
      message: 'Only a request on hold has an expiry to change; this one is pending.',
    })
  })

  it('holds the new expiry to the same limits as the first (400 on expires_at)', async () => {
    await hold(BREAKOUT_ROOM)

    const error = await refusalOf(
      changeHoldExpiry(BREAKOUT_ROOM, { expires_at: '2026-11-21T09:00:00+08:00' }),
    )

    expect(error.fieldErrors).toEqual({
      expires_at: ['The expiry must be before the event starts.'],
    })
  })
})

describe('SCRUM-75 booking mock: final approval or rejection of a hold', () => {
  it.each([
    ['approved', 'approved'],
    ['rejected', 'rejected'],
  ] as const)('%s, it leaves the queue with no expiry shown', async (outcome, status) => {
    await hold(BREAKOUT_ROOM)

    const decided = await decideBookingRequest(BREAKOUT_ROOM, { outcome, reason: 'Finalised' })

    expect(decided).toMatchObject({ status, hold_expires_at: null })
    expect(statusIn(await fetchPendingBookingRequests(), BREAKOUT_ROOM)).toBeUndefined()
  })
})

describe('SCRUM-75 booking mock: who may hold', () => {
  const CALLS = {
    'place a hold': (requestId: number) => hold(requestId),
    'change an expiry': (requestId: number) =>
      changeHoldExpiry(requestId, { expires_at: LATER_BEFORE_THE_WORKSHOP }),
  }

  it.each(Object.entries(CALLS))('refuses to %s without a token (401)', async (_name, call) => {
    signInAs(null)

    expect(await refusalOf(call(BREAKOUT_ROOM))).toMatchObject({
      status: 401,
      code: 'authentication_error',
    })
  })

  it.each(
    Object.entries(CALLS).flatMap(([name, call]) =>
      accountsOfEveryRoleBut(ROLE.VENUE_STAFF).map(([role, account]) => ({
        name,
        call,
        role,
        account,
      })),
    ),
  )('refuses to let $role $name (403)', async ({ call, account }) => {
    signInAs(account)

    expect(await refusalOf(call(BREAKOUT_ROOM))).toMatchObject({
      status: 403,
      code: 'authorization_error',
    })
  })

  it.each(Object.entries(CALLS))(
    'answers 404 to %s on a request that does not exist',
    async (_name, call) => {
      expect(await refusalOf(call(99_999))).toMatchObject({
        status: 404,
        code: 'not_found',
        message: 'Booking request not found.',
      })
    },
  )
})
