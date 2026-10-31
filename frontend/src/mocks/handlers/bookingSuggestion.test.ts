import {
  decideBookingRequest,
  fetchBookingRequests,
  fetchPendingBookingRequests,
  raiseBookingRequest,
} from '@/features/booking/api'
import type { BookingDecision } from '@/features/booking/api'
import { refusalOf } from '@/test/refusalOf'

import { MOCK_ACCOUNTS } from '../fixtures/accounts'

import { everyArrangementForRecord } from './booking'
import { MOCK_ARRANGEMENTS, MOCK_BOOKING_EVENTS, MOCK_BOOKING_VENUES } from './bookingFixtures'
import { signInAs } from './test/eventRequestCalls'
import { MOCK_VENUES } from './venueFixtures'

/**
 * The booking mock's suggested alternative (SCRUM-70, ADR-0123), pinned to what
 * backend/app/modules/venue/services.py answers, messages included. Main hall (9002) waits for a
 * decision; Garden Pavilion is active and Archive Studio is not.
 */

const MAIN_HALL = 9002
const GARDEN_PAVILION = MOCK_VENUES.gardenPavilion
const ARCHIVE_STUDIO = MOCK_VENUES.archiveStudio
const SUGGESTED_PERIOD = {
  suggested_starts_at: '2026-12-02T10:00:00+08:00',
  suggested_ends_at: '2026-12-02T16:00:00+08:00',
}
const ONLY_WHEN_REJECTING = 'An alternative can only be suggested when rejecting a request.'
const NOT_ACTIVE = 'The suggested venue must be an active venue.'
const PERIOD_LOCKED =
  'A replacement keeps the period of the booking it replaces, so only another venue can be suggested.'

function reject(requestId: number, suggestion: Omit<BookingDecision, 'outcome'> = {}) {
  return decideBookingRequest(requestId, { outcome: 'rejected', reason: 'Closed', ...suggestion })
}

async function stillWaiting(requestId: number): Promise<boolean> {
  const queue = await fetchPendingBookingRequests()
  return queue.some((waiting) => waiting.id === requestId)
}

beforeEach(() => {
  signInAs(MOCK_ACCOUNTS.venueStaff)
})

describe('SCRUM-70 booking mock: suggesting an alternative when rejecting', () => {
  it('keeps a suggested venue and period on the rejected request', async () => {
    const rejected = await reject(MAIN_HALL, {
      suggested_venue_id: GARDEN_PAVILION.id,
      ...SUGGESTED_PERIOD,
    })

    expect(rejected).toMatchObject({
      status: 'rejected',
      decision_reason: 'Closed',
      suggested_venue_id: GARDEN_PAVILION.id,
      ...SUGGESTED_PERIOD,
    })
  })

  it('leaves each part of a suggestion not given null', async () => {
    const rejected = await reject(MAIN_HALL, { suggested_venue_id: GARDEN_PAVILION.id })

    expect(rejected).toMatchObject({ suggested_starts_at: null, suggested_ends_at: null })
  })

  it('shows the suggestion to the coordinator, beside the reason', async () => {
    await reject(MAIN_HALL, { suggested_venue_id: GARDEN_PAVILION.id, ...SUGGESTED_PERIOD })
    signInAs(MOCK_ACCOUNTS.coordinator)

    const listed = await fetchBookingRequests(MOCK_BOOKING_EVENTS.laterShowcase.reference)

    expect(listed.find((each) => each.id === MAIN_HALL)).toMatchObject({
      decision_reason: 'Closed',
      suggested_venue_id: GARDEN_PAVILION.id,
      ...SUGGESTED_PERIOD,
    })
  })

  it('shows the suggested venue by name on the event record', async () => {
    await reject(MAIN_HALL, { suggested_venue_id: GARDEN_PAVILION.id, ...SUGGESTED_PERIOD })

    const [shown] = everyArrangementForRecord(MOCK_BOOKING_EVENTS.laterShowcase.reference)

    expect(shown).toMatchObject({
      suggested_venue_name: 'Garden Pavilion',
      ...SUGGESTED_PERIOD,
    })
  })

  it('refuses a suggestion with an approval, on each field given', async () => {
    const error = await refusalOf(
      decideBookingRequest(MAIN_HALL, { outcome: 'approved', ...SUGGESTED_PERIOD }),
    )

    expect(error).toMatchObject({ status: 400, code: 'validation_error' })
    expect(error.fieldErrors).toEqual({
      suggested_starts_at: [ONLY_WHEN_REJECTING],
      suggested_ends_at: [ONLY_WHEN_REJECTING],
    })
    expect(await stillWaiting(MAIN_HALL)).toBe(true)
  })

  it.each([
    ['an inactive venue', ARCHIVE_STUDIO.id],
    ['a venue that does not exist', 999],
  ])('refuses %s', async (_case, venueId) => {
    const error = await refusalOf(reject(MAIN_HALL, { suggested_venue_id: venueId }))

    expect(error.fieldErrors).toEqual({ suggested_venue_id: [NOT_ACTIVE] })
    expect(await stillWaiting(MAIN_HALL)).toBe(true)
  })

  it.each([
    [
      'a start with no end',
      { suggested_starts_at: SUGGESTED_PERIOD.suggested_starts_at },
      { suggested_ends_at: ['A suggested period needs both a start and an end.'] },
    ],
    [
      'an end with no start',
      { suggested_ends_at: SUGGESTED_PERIOD.suggested_ends_at },
      { suggested_starts_at: ['A suggested period needs both a start and an end.'] },
    ],
    [
      'an end before the start',
      {
        suggested_starts_at: SUGGESTED_PERIOD.suggested_ends_at,
        suggested_ends_at: SUGGESTED_PERIOD.suggested_starts_at,
      },
      { suggested_ends_at: ['suggested_ends_at must be after suggested_starts_at.'] },
    ],
    [
      'times that are not times',
      { suggested_starts_at: 'soon', suggested_ends_at: 'later' },
      {
        suggested_starts_at: ['Not a valid datetime.'],
        suggested_ends_at: ['Not a valid datetime.'],
      },
    ],
  ])('refuses %s', async (_case, period, fieldErrors) => {
    const error = await refusalOf(reject(MAIN_HALL, period))

    expect(error.fieldErrors).toEqual(fieldErrors)
  })

  it('refuses a venue id that is not a whole number from 1', async () => {
    const error = await refusalOf(reject(MAIN_HALL, { suggested_venue_id: 0 }))

    expect(error.fieldErrors).toEqual({
      suggested_venue_id: ['suggested_venue_id must be a positive number.'],
    })
  })

  it('leaves the whole-period check out once a field is refused, as the schema does', async () => {
    // Marshmallow skips a schema-wide check after a field error, so half a period goes unsaid.
    const halfPeriod = { suggested_starts_at: SUGGESTED_PERIOD.suggested_starts_at }

    const error = await refusalOf(reject(MAIN_HALL, { suggested_venue_id: 0, ...halfPeriod }))

    expect(error.fieldErrors).toEqual({
      suggested_venue_id: ['suggested_venue_id must be a positive number.'],
    })
  })
})

describe('SCRUM-70 booking mock: a replacement for an unavailable venue keeps its period', () => {
  const FLAGGED_HALL = MOCK_ARRANGEMENTS.bookedHall

  /** As the coordinator, replace the flagged hall at the tiny venue; answers the replacement's id. */
  async function replaceTheFlaggedHall(): Promise<number> {
    signInAs(MOCK_ACCOUNTS.coordinator)
    const replacement = await raiseBookingRequest(MOCK_BOOKING_EVENTS.booked.reference, {
      venue_id: MOCK_BOOKING_VENUES.tiny.id,
      starts_at: FLAGGED_HALL.starts_at,
      ends_at: FLAGGED_HALL.ends_at,
      purpose: 'Replacement hall',
      expected_occupancy: 10,
      replaces_request_id: FLAGGED_HALL.id,
    })
    signInAs(MOCK_ACCOUNTS.venueStaff)
    return replacement.id
  }

  it('refuses another period', async () => {
    const replacement = await replaceTheFlaggedHall()

    const error = await refusalOf(reject(replacement, SUGGESTED_PERIOD))

    expect(error.fieldErrors).toEqual({
      suggested_starts_at: [PERIOD_LOCKED],
      suggested_ends_at: [PERIOD_LOCKED],
    })
  })

  it('takes another venue', async () => {
    const replacement = await replaceTheFlaggedHall()

    const rejected = await reject(replacement, { suggested_venue_id: GARDEN_PAVILION.id })

    expect(rejected.suggested_venue_id).toBe(GARDEN_PAVILION.id)
  })

  it('takes another period for a replacement of a booking flagged only after a change', async () => {
    // Its venue is still there, so its period may move (ADR-0100), as the backend allows.
    const changedHall = MOCK_ARRANGEMENTS.movedHall
    signInAs(MOCK_ACCOUNTS.coordinator)
    const replacement = await raiseBookingRequest(MOCK_BOOKING_EVENTS.moved.reference, {
      venue_id: MOCK_BOOKING_VENUES.tiny.id,
      starts_at: changedHall.starts_at,
      ends_at: changedHall.ends_at,
      purpose: 'Replacement hall',
      expected_occupancy: 10,
      replaces_request_id: changedHall.id,
    })
    signInAs(MOCK_ACCOUNTS.venueStaff)

    const rejected = await reject(replacement.id, SUGGESTED_PERIOD)

    expect([rejected.suggested_starts_at, rejected.suggested_ends_at]).toEqual([
      SUGGESTED_PERIOD.suggested_starts_at,
      SUGGESTED_PERIOD.suggested_ends_at,
    ])
  })
})
