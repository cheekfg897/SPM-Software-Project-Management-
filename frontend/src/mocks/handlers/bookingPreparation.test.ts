import { ROLE } from '@/config/roles'
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

/**
 * Every account but Venue Staff's. The backend's requires_role(Role.VENUE_STAFF) refuses each of
 * them, so the list is built from the accounts and a role added later is checked too.
 */
const NOT_VENUE_STAFF = Object.values(MOCK_ACCOUNTS).filter(
  (account) => account.role !== ROLE.VENUE_STAFF,
)

/** The status each account but Venue Staff's gets back from `send`, by role. */
async function statusesForOtherRoles(send: () => Promise<unknown>) {
  const statuses = []
  for (const account of NOT_VENUE_STAFF) {
    sendRequestsAs(mockTokenFor(account))
    const error = await refusalOf(send())
    statuses.push({ role: account.role, status: error.status })
  }
  return statuses
}

function refusedToEveryone() {
  return NOT_VENUE_STAFF.map((account) => ({ role: account.role, status: 403 }))
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
      // Flagged as needing an alternative venue, but still approved until a replacement is (SCRUM-92).
      MOCK_ARRANGEMENTS.reviewedAuditorium.id,
      // The confirmed gala's two, which share its date and start, so by id.
      MOCK_ARRANGEMENTS.galaDinner.id,
      MOCK_ARRANGEMENTS.galaReception.id,
    ])
  })

  it('answers 401 without a token and 403 to every role but Venue Staff', async () => {
    sendRequestsAs(null)
    expect(await refusalOf(listApproved())).toMatchObject({ status: 401 })

    expect(await statusesForOtherRoles(listApproved)).toEqual(refusedToEveryone())
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

  it('refuses any other field, as the booking is all it may change (AC3, 400)', async () => {
    const error = await refusalOf(
      prepare(SAFETY_APPROVED_BOOKING.id, { status: 'ready', venue_id: 2, purpose: 'Changed' }),
    )

    expect(error.fieldErrors).toEqual({ venue_id: ['Unknown field.'], purpose: ['Unknown field.'] })
    expect(await listedCopyOf(SAFETY_APPROVED_BOOKING.id)).toMatchObject({
      purpose: 'Grand ballroom',
      preparation_status: 'in_progress',
    })
  })

  it("refuses a null status and notes that aren't text, as the backend's schema does (400)", async () => {
    const nullStatus = await refusalOf(prepare(SAFETY_APPROVED_BOOKING.id, { status: null }))
    const numberNotes = await refusalOf(
      prepare(SAFETY_APPROVED_BOOKING.id, { status: 'ready', notes: 5 }),
    )
    const booleanStatus = await refusalOf(
      prepare(SAFETY_APPROVED_BOOKING.id, { status: true, notes: false }),
    )

    expect(nullStatus.fieldErrors).toEqual({ status: ['Field may not be null.'] })
    expect(numberNotes.fieldErrors).toEqual({ notes: ['Not a valid string.'] })
    expect(booleanStatus.fieldErrors).toEqual({
      status: ['Status must be not_started, in_progress or ready.'],
      notes: ['Not a valid string.'],
    })
  })

  it('takes null notes as left out, clearing them', async () => {
    const saved = await prepare(SAFETY_APPROVED_BOOKING.id, { status: 'ready', notes: null })

    expect(saved).toMatchObject({ preparation_status: 'ready', preparation_notes: null })
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

  it('answers 401 without a token and 403 to every role but Venue Staff', async () => {
    sendRequestsAs(null)
    expect(await refusalOf(prepare(SAFETY_APPROVED_BOOKING.id, {}))).toMatchObject({
      status: 401,
    })

    const statuses = await statusesForOtherRoles(() =>
      prepare(SAFETY_APPROVED_BOOKING.id, { status: 'ready' }),
    )

    expect(statuses).toEqual(refusedToEveryone())
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
