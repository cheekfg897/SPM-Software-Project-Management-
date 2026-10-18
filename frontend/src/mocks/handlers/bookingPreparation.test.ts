import { apiRequest } from '@/lib/api'
import { refusalOf } from '@/test/refusalOf'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { MOCK_ACCOUNTS, mockTokenFor } from '../fixtures/accounts'

import { MOCK_ARRANGEMENTS, MOCK_BOOKING_EVENTS, MOCK_PENDING_DECISIONS } from './bookingFixtures'
import { PREPARATION_NEEDS_SAFETY_APPROVAL_MESSAGE } from './preparationRules'

/**
 * The booking mock's SCRUM-84 endpoints: Venue Staff's approved bookings (ADR-0080) and the
 * preparation update, pinned to what backend/app/modules/venue/routes.py answers.
 */

const APPROVED_URL = '/api/venues/booking-requests/approved'
/** Approved, on the event the Safety Officer has approved. */
const SAFETY_APPROVED_BOOKING = MOCK_ARRANGEMENTS.preparedBallroom
/** Approved, but its event is still waiting for the Safety Officer. */
const AWAITING_SAFETY_BOOKING = MOCK_ARRANGEMENTS.bookedHall

function preparationUrl(requestId: number): string {
  return `/api/venues/booking-requests/${requestId}/preparation`
}

function listApproved() {
  return apiRequest<Record<string, unknown>[]>(APPROVED_URL)
}

/** One booking as the approved list now shows it. */
async function listedCopyOf(bookingId: number) {
  const listed = await listApproved()
  return listed.find((booking) => booking.id === bookingId)
}

function prepare(requestId: number, body: Record<string, unknown>) {
  return apiRequest<Record<string, unknown>>(preparationUrl(requestId), { method: 'PUT', body })
}

beforeEach(() => {
  sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.venueStaff))
})

describe('SCRUM-84 booking mock: the approved bookings', () => {
  it('lists only approved bookings, the earliest event first', async () => {
    const listed = await listApproved()

    expect(listed.map((booking) => booking.id)).toEqual([
      SAFETY_APPROVED_BOOKING.id,
      MOCK_ARRANGEMENTS.exhibitionHall.id,
      AWAITING_SAFETY_BOOKING.id,
    ])
  })

  it('answers 401 without a token and 403 to anyone but Venue Staff', async () => {
    sendRequestsAs(null)
    expect(await refusalOf(listApproved())).toMatchObject({ status: 401 })

    sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.coordinator))
    expect(await refusalOf(listApproved())).toMatchObject({ status: 403 })
  })
})

describe('SCRUM-84 booking mock: recording preparation', () => {
  it('saves the status and the trimmed notes, and lists them after', async () => {
    const saved = await prepare(SAFETY_APPROVED_BOOKING.id, {
      status: 'ready',
      notes: '  Room ready.  ',
    })

    expect(saved).toMatchObject({ preparation_status: 'ready', preparation_notes: 'Room ready.' })
    expect(await listedCopyOf(SAFETY_APPROVED_BOOKING.id)).toMatchObject({
      preparation_status: 'ready',
    })
  })

  it('clears the notes when they are left out', async () => {
    const saved = await prepare(SAFETY_APPROVED_BOOKING.id, { status: 'ready' })

    expect(saved).toMatchObject({ preparation_notes: null })
  })

  it('names a missing or unknown status, and blank or overlong notes (400)', async () => {
    const missing = await refusalOf(prepare(SAFETY_APPROVED_BOOKING.id, { notes: '   ' }))
    const unknown = await refusalOf(
      prepare(SAFETY_APPROVED_BOOKING.id, { status: 'done', notes: 'x'.repeat(1001) }),
    )

    expect(missing.fieldErrors).toEqual({
      status: ['Missing data for required field.'],
      notes: ['Must not be blank.'],
    })
    expect(unknown.fieldErrors).toEqual({
      status: ['Status must be not_started, in_progress or ready.'],
      notes: ['Notes must be at most 1000 characters.'],
    })
  })

  it('answers 404 for a booking that does not exist', async () => {
    const error = await refusalOf(prepare(1, { status: 'ready' }))

    expect(error).toMatchObject({ status: 404, message: 'Booking request not found.' })
  })

  it('refuses a booking that is not approved, naming its status (409)', async () => {
    const [pending] = MOCK_PENDING_DECISIONS

    const error = await refusalOf(prepare(pending.id, { status: 'ready' }))

    expect(error).toMatchObject({
      status: 409,
      message: 'Preparation can only be recorded for an approved booking; this one is pending.',
    })
  })

  it('refuses an event the Safety Officer has not approved, saving nothing (409)', async () => {
    const error = await refusalOf(prepare(AWAITING_SAFETY_BOOKING.id, { status: 'ready' }))

    expect(error).toMatchObject({ status: 409, message: PREPARATION_NEEDS_SAFETY_APPROVAL_MESSAGE })
    expect(await listedCopyOf(AWAITING_SAFETY_BOOKING.id)).toMatchObject({
      preparation_status: 'not_started',
    })
  })

  it('answers 401 without a token and 403 to anyone but Venue Staff', async () => {
    sendRequestsAs(null)
    expect(await refusalOf(prepare(SAFETY_APPROVED_BOOKING.id, {}))).toMatchObject({
      status: 401,
    })

    sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.coordinator))
    expect(await refusalOf(prepare(SAFETY_APPROVED_BOOKING.id, {}))).toMatchObject({
      status: 403,
    })
  })
})

describe('SCRUM-84 booking mock: the coordinator reads preparation', () => {
  it('shows the coordinator the preparation on the bookings of their event (AC2)', async () => {
    sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.coordinator))
    const reference = MOCK_BOOKING_EVENTS.safetyApproved.reference

    const listed = await apiRequest<Record<string, unknown>[]>(
      `/api/venues/events/${reference}/booking-requests`,
    )

    expect(listed).toEqual([
      expect.objectContaining({
        id: SAFETY_APPROVED_BOOKING.id,
        preparation_status: 'in_progress',
        preparation_notes: 'Stage half built.',
      }),
    ])
  })
})
