import type { BookingRequest, FlaggedBooking } from '@/features/booking/api'
import { ApiError, apiRequest } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { MOCK_ACCOUNTS, mockTokenFor } from '../fixtures/accounts'

import { flagArrangementsAfterChange } from './booking'
import { MOCK_ARRANGEMENTS, MOCK_BOOKING_EVENTS, MOCK_BOOKING_VENUES } from './bookingFixtures'

/**
 * SCRUM-59: the booking mock stands in for the venue module's flagged-booking routes, so these
 * tests pin it to what backend/app/modules/venue/routes.py answers: the list with what
 * reconfirming each booking gives it, the reconfirmation and the rejection, refusals and side
 * effects included.
 */

const FLAGGED_PATH = '/api/venues/booking-requests/flagged'
const HALL = MOCK_ARRANGEMENTS.movedHall
const WORKSHOP = MOCK_ARRANGEMENTS.movedWorkshop
const STAGE = MOCK_ARRANGEMENTS.movedStage
const ANNEX = MOCK_ARRANGEMENTS.movedAnnex
const MOVED_EVENT = MOCK_BOOKING_EVENTS.moved
const REASON = 'The hall is booked for exams that day.'

function reconfirmPath(id: number): string {
  return `/api/venues/booking-requests/${String(id)}/reconfirm`
}

function rejectPath(id: number): string {
  return `/api/venues/booking-requests/${String(id)}/reject`
}

function signInAsVenueStaff() {
  sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.venueStaff))
}

function signInAsCoordinator() {
  sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.coordinator))
}

function listFlagged() {
  return apiRequest<FlaggedBooking[]>(FLAGGED_PATH)
}

function reconfirm(id: number, body: Record<string, unknown>) {
  return apiRequest<BookingRequest>(reconfirmPath(id), { method: 'POST', body })
}

function reject(id: number, body: Record<string, unknown>) {
  return apiRequest<BookingRequest>(rejectPath(id), { method: 'POST', body })
}

/** A period on the moved event's new day, 16 November, in business time. */
function onTheNewDay(starts: string, ends: string) {
  return { starts_at: `2026-11-16T${starts}:00+08:00`, ends_at: `2026-11-16T${ends}:00+08:00` }
}

async function errorOf(promise: Promise<unknown>): Promise<ApiError> {
  const error: unknown = await promise.then(
    () => null,
    (caught: unknown) => caught,
  )
  if (!(error instanceof ApiError)) {
    throw new Error('Expected the request to fail with an ApiError.')
  }
  return error
}

/** Raise a request as the coordinator, then sign Venue Staff back in. */
async function raiseAsCoordinator(reference: string, body: Record<string, unknown>) {
  signInAsCoordinator()
  const raised = await apiRequest<BookingRequest>(
    `/api/venues/events/${reference}/booking-requests`,
    { method: 'POST', body },
  )
  signInAsVenueStaff()
  return raised
}

const HOUR_MS = 60 * 60_000
const EXHIBITION = MOCK_ARRANGEMENTS.exhibitionHall

/**
 * A change to the earlier workshop that moved its start and end by as much, and changed its venue
 * requirements, so its exhibition hall (13:00-16:00 on 20 November) is flagged whatever the move.
 */
function flagWorkshopAfterChange(startMovedByMs: number, endMovedByMs: number) {
  flagArrangementsAfterChange(MOCK_BOOKING_EVENTS.earlierWorkshop.reference, {
    timingChanged: startMovedByMs !== 0 || endMovedByMs !== 0,
    venueRequirementsChanged: true,
    previousAttendance: 80,
    newAttendance: 80,
    startMovedByMs,
    endMovedByMs,
  })
}

async function exhibitionReconfirmation() {
  const flagged = await listFlagged()
  return flagged.find((entry) => entry.booking.id === EXHIBITION.id)?.reconfirm_with
}

beforeEach(signInAsVenueStaff)

describe('SCRUM-59 booking mock: the flagged bookings', () => {
  it('refuses a caller without a token (401) and a role other than Venue Staff (403)', async () => {
    sendRequestsAs(null)
    const anonymous = await errorOf(listFlagged())
    signInAsCoordinator()
    const coordinator = await errorOf(listFlagged())

    expect([anonymous.status, coordinator.status]).toEqual([401, 403])
  })

  it('lists each live booking a change flagged, with what reconfirming it gives it', async () => {
    const flagged = await listFlagged()

    expect(flagged.map((entry) => entry.booking.id)).toEqual([HALL.id, WORKSHOP.id, STAGE.id])
    expect(flagged.map((entry) => entry.reconfirm_with)).toEqual([
      { ...onTheNewDay('09:00', '12:00'), expected_occupancy: 120, period_adjustable: true },
      { ...onTheNewDay('13:00', '15:00'), expected_occupancy: 10, period_adjustable: true },
      { ...onTheNewDay('15:30', '17:00'), expected_occupancy: 120, period_adjustable: true },
    ])
  })

  it('leaves out a booking that needs an alternative venue, and every one not flagged', async () => {
    const ids = (await listFlagged()).map((entry) => entry.booking.id)

    expect(ids).not.toContain(ANNEX.id)
    expect(ids).not.toContain(MOCK_ARRANGEMENTS.bookedHall.id)
    expect(ids).not.toContain(MOCK_ARRANGEMENTS.exhibitionHall.id)
  })

  it('lists a booking an edit flags, moved by as much as the edit moved the start', async () => {
    flagWorkshopAfterChange(2 * HOUR_MS, 2 * HOUR_MS)

    expect(await exhibitionReconfirmation()).toEqual({
      starts_at: '2026-11-20T15:00:00+08:00',
      ends_at: '2026-11-20T18:00:00+08:00',
      expected_occupancy: 10,
      period_adjustable: true,
    })
  })

  // ADR-0112 decision 17: the period may be adjusted only once the event's start or end moved.
  it.each([
    ['moved only its end', 0, HOUR_MS, true],
    ['left its date and times', 0, 0, false],
  ])(
    'says whether the period may be adjusted after a change that %s',
    async (_label, start, end, adjustable) => {
      flagWorkshopAfterChange(start, end)

      expect(await exhibitionReconfirmation()).toEqual({
        starts_at: '2026-11-20T13:00:00+08:00',
        ends_at: '2026-11-20T16:00:00+08:00',
        expected_occupancy: 10,
        period_adjustable: adjustable,
      })
    },
  )
})

describe('SCRUM-59 booking mock: reconfirming a flagged booking', () => {
  it('refuses a caller without a token (401) and a role other than Venue Staff (403)', async () => {
    sendRequestsAs(null)
    const anonymous = await errorOf(reconfirm(HALL.id, onTheNewDay('09:00', '12:00')))
    signInAsCoordinator()
    const coordinator = await errorOf(reconfirm(HALL.id, onTheNewDay('09:00', '12:00')))

    expect([anonymous.status, coordinator.status]).toEqual([401, 403])
  })

  it('moves an approved booking, raises its occupancy and clears its flags', async () => {
    const reconfirmed = await reconfirm(HALL.id, onTheNewDay('09:00', '12:00'))

    expect(reconfirmed).toMatchObject({
      status: 'approved',
      ...onTheNewDay('09:00', '12:00'),
      expected_occupancy: 120,
      flagged_after_change: false,
      reassessment_flags: [],
    })
    expect((await listFlagged()).map((entry) => entry.booking.id)).not.toContain(HALL.id)
    const approved = await apiRequest<BookingRequest[]>('/api/venues/booking-requests/approved')
    expect(approved.find((booking) => booking.id === HALL.id)).toMatchObject(
      onTheNewDay('09:00', '12:00'),
    )
  })

  it('only moves a request Venue Staff have not decided, which waits in the queue', async () => {
    await reconfirm(WORKSHOP.id, onTheNewDay('13:00', '15:00'))

    const queue = await apiRequest<BookingRequest[]>('/api/venues/booking-requests')
    expect(queue.find((request) => request.id === WORKSHOP.id)).toMatchObject({
      status: 'pending',
      ...onTheNewDay('13:00', '15:00'),
      flagged_after_change: false,
    })
  })

  it('moves a Conflicting request back to Pending', async () => {
    const clashing = await raiseAsCoordinator(MOVED_EVENT.reference, {
      venue_id: MOCK_BOOKING_VENUES.tiny.id,
      starts_at: '2026-11-15T13:30:00+08:00',
      ends_at: '2026-11-15T14:00:00+08:00',
      purpose: 'Green room',
      expected_occupancy: 10,
    })
    await apiRequest(`/api/venues/booking-requests/${String(clashing.id)}/decision`, {
      method: 'POST',
      body: { outcome: 'approved' },
    })

    const moved = await reconfirm(WORKSHOP.id, onTheNewDay('13:00', '15:00'))

    expect(moved.status).toBe('pending')
  })

  it('keeps a trimmed reason as Venue Staff reason for a venue too small', async () => {
    const reconfirmed = await reconfirm(STAGE.id, {
      ...onTheNewDay('15:30', '17:00'),
      reason: '  Standing room agreed.  ',
    })

    expect(reconfirmed).toMatchObject({
      expected_occupancy: 120,
      decision_reason: 'Standing room agreed.',
    })
  })

  it.each([
    ['missing', {}],
    ['blank', { reason: '   ' }],
  ])('needs a reason for a venue too small (%s)', async (_label, reason) => {
    const error = await errorOf(
      reconfirm(STAGE.id, { ...onTheNewDay('15:30', '17:00'), ...reason }),
    )

    expect([error.status, error.fieldErrors]).toEqual([
      400,
      {
        reason: [
          "A reason is required because the venue's capacity of 20 is below the booking's expected occupancy of 120.",
        ],
      },
    ])
  })

  it('marks another event pending request the new period overlaps Conflicting', async () => {
    const other = await raiseAsCoordinator(MOCK_BOOKING_EVENTS.approved.reference, {
      venue_id: MOCK_BOOKING_VENUES.roomy.id,
      ...onTheNewDay('10:00', '11:00'),
      purpose: 'Board meeting',
    })

    await reconfirm(HALL.id, onTheNewDay('09:00', '12:00'))

    const queue = await apiRequest<BookingRequest[]>('/api/venues/booking-requests')
    expect(queue.find((request) => request.id === other.id)?.status).toBe('conflicting')
  })

  it('refuses a period outside the event, naming the event times', async () => {
    const error = await errorOf(
      reconfirm(HALL.id, {
        starts_at: '2026-11-15T09:00:00+08:00',
        ends_at: '2026-11-16T18:00:00+08:00',
      }),
    )

    const message =
      "The period must lie within the event's start and end: 2026-11-16 09:00 to 2026-11-16 17:00."
    expect([error.status, error.fieldErrors]).toEqual([
      400,
      { starts_at: [message], ends_at: [message] },
    ])
  })

  it('refuses a period that runs into another approved booking at the venue', async () => {
    await reconfirm(STAGE.id, { ...onTheNewDay('15:30', '17:00'), reason: 'Agreed.' })

    const error = await errorOf(reconfirm(WORKSHOP.id, onTheNewDay('15:00', '16:00')))

    expect([error.status, error.message]).toEqual([
      409,
      `Cannot reconfirm: booking #${String(STAGE.id)} holds this venue from 2026-11-16 15:30 to 2026-11-16 17:00, setup and turnaround included.`,
    ])
  })

  it('refuses a period that overlaps another of the event requests at the venue', async () => {
    await reconfirm(WORKSHOP.id, onTheNewDay('13:00', '15:00'))

    const error = await errorOf(
      reconfirm(STAGE.id, { ...onTheNewDay('14:00', '16:00'), reason: 'Agreed.' }),
    )

    expect([error.status, error.message]).toEqual([
      409,
      `Cannot reconfirm: the new period overlaps venue arrangement #${String(WORKSHOP.id)} of the same event at this venue.`,
    ])
  })

  it('waits while a replacement for the booking is waiting for a decision', async () => {
    const replacement = await raiseAsCoordinator(MOVED_EVENT.reference, {
      venue_id: MOCK_BOOKING_VENUES.roomy.id,
      ...onTheNewDay('13:00', '14:00'),
      purpose: 'Replacement hall',
      replaces_request_id: HALL.id,
    })

    const error = await errorOf(reconfirm(HALL.id, onTheNewDay('09:00', '12:00')))

    expect([error.status, error.message]).toEqual([
      409,
      `Cannot reconfirm: replacement request #${String(replacement.id)} for this booking is still waiting for a decision.`,
    ])
  })

  it('refuses an unknown booking (404), one not flagged and one needing another venue (409)', async () => {
    const unknown = await errorOf(reconfirm(404, onTheNewDay('09:00', '12:00')))
    const notFlagged = await errorOf(
      reconfirm(MOCK_ARRANGEMENTS.exhibitionHall.id, onTheNewDay('09:00', '12:00')),
    )
    const annex = await errorOf(reconfirm(ANNEX.id, onTheNewDay('13:00', '14:00')))

    expect([unknown.status, unknown.message]).toEqual([404, 'Booking request not found.'])
    expect([notFlagged.status, notFlagged.message]).toEqual([
      409,
      'This booking is not flagged after a change, so there is nothing to reconfirm or reject.',
    ])
    expect([annex.status, annex.message]).toEqual([
      409,
      'This booking needs an alternative venue, which only a replacement settles.',
    ])
  })

  it.each([
    [
      'no start',
      { ends_at: '2026-11-16T12:00:00+08:00' },
      { starts_at: ['Missing data for required field.'] },
    ],
    [
      'not a date-time',
      { starts_at: 'Monday', ends_at: '2026-11-16T12:00:00+08:00' },
      { starts_at: ['Not a valid datetime.'] },
    ],
    [
      'ends first',
      onTheNewDay('12:00', '09:00'),
      { ends_at: ['ends_at must be after starts_at.'] },
    ],
    [
      'unknown field',
      { ...onTheNewDay('09:00', '12:00'), status: 'approved' },
      { status: ['Unknown field.'] },
    ],
    [
      'number reason',
      { ...onTheNewDay('09:00', '12:00'), reason: 7 },
      { reason: ['Not a valid string.'] },
    ],
    [
      'boolean reason',
      { ...onTheNewDay('09:00', '12:00'), reason: true },
      { reason: ['Not a valid string.'] },
    ],
    [
      'list reason',
      { ...onTheNewDay('09:00', '12:00'), reason: ['A'] },
      { reason: ['Not a valid string.'] },
    ],
  ])('refuses a body with %s, as the schema does', async (_label, body, fieldErrors) => {
    const error = await errorOf(reconfirm(HALL.id, body))

    expect([error.status, error.fieldErrors]).toEqual([400, fieldErrors])
  })

  it("refuses a new period for a booking the change didn't retime, and keeps its own", async () => {
    flagWorkshopAfterChange(0, 0)
    const ownPeriod = {
      starts_at: '2026-11-20T13:00:00+08:00',
      ends_at: '2026-11-20T16:00:00+08:00',
    }

    const error = await errorOf(
      reconfirm(EXHIBITION.id, { ...ownPeriod, starts_at: '2026-11-20T14:00:00+08:00' }),
    )
    const kept = await reconfirm(EXHIBITION.id, ownPeriod)

    expect([error.status, error.fieldErrors]).toEqual([
      400,
      {
        starts_at: [
          "The event's date and times haven't changed, so the booking keeps its period: 2026-11-20 13:00 to 2026-11-20 16:00.",
        ],
      },
    ])
    expect(kept).toMatchObject({ ...ownPeriod, flagged_after_change: false })
  })

  it('takes a null reason as no reason, as the schema does', async () => {
    const reconfirmed = await reconfirm(HALL.id, { ...onTheNewDay('09:00', '12:00'), reason: null })

    expect(reconfirmed).toMatchObject({ status: 'approved', flagged_after_change: false })
  })
})

describe('SCRUM-59 booking mock: rejecting a flagged booking', () => {
  it('refuses a caller without a token (401) and a role other than Venue Staff (403)', async () => {
    sendRequestsAs(null)
    const anonymous = await errorOf(reject(HALL.id, { reason: REASON }))
    signInAsCoordinator()
    const coordinator = await errorOf(reject(HALL.id, { reason: REASON }))

    expect([anonymous.status, coordinator.status]).toEqual([401, 403])
  })

  it('rejects an approved booking with the reason and frees its venue', async () => {
    const rejected = await reject(HALL.id, { reason: `  ${REASON}  ` })

    expect(rejected).toMatchObject({
      status: 'rejected',
      decision_reason: REASON,
      flagged_after_change: false,
      reassessment_flags: HALL.reassessment_flags,
    })
    expect((await listFlagged()).map((entry) => entry.booking.id)).not.toContain(HALL.id)
    const approved = await apiRequest<BookingRequest[]>('/api/venues/booking-requests/approved')
    expect(approved.map((booking) => booking.id)).not.toContain(HALL.id)
  })

  it('rejects a request Venue Staff have not decided, which leaves the queue', async () => {
    await reject(WORKSHOP.id, { reason: REASON })

    const queue = await apiRequest<BookingRequest[]>('/api/venues/booking-requests')
    expect(queue.map((request) => request.id)).not.toContain(WORKSHOP.id)
  })

  it.each([
    ['missing', {}],
    ['blank', { reason: '  ' }],
    ['null', { reason: null }],
  ])('needs a reason (%s)', async (_label, body) => {
    const error = await errorOf(reject(HALL.id, body))

    expect([error.status, error.fieldErrors]).toEqual([
      400,
      { reason: ['A reason is required to reject a booking request.'] },
    ])
  })

  it.each([
    ['number', { reason: 7 }, { reason: ['Not a valid string.'] }],
    ['unknown field', { reason: REASON, status: 'rejected' }, { status: ['Unknown field.'] }],
  ])('refuses a body with a %s, as the schema does', async (_label, body, fieldErrors) => {
    const error = await errorOf(reject(HALL.id, body))

    expect([error.status, error.fieldErrors]).toEqual([400, fieldErrors])
  })

  it('refuses an unknown booking (404), one not flagged and one needing another venue (409)', async () => {
    const unknown = await errorOf(reject(404, { reason: REASON }))
    const notFlagged = await errorOf(
      reject(MOCK_ARRANGEMENTS.exhibitionHall.id, { reason: REASON }),
    )
    const annex = await errorOf(reject(ANNEX.id, { reason: REASON }))

    expect([unknown.status, notFlagged.status, annex.status]).toEqual([404, 409, 409])
  })
})
