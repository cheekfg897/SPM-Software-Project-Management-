import {
  blockVenue,
  createVenue,
  deactivateVenue,
  fetchVenue,
  fetchVenueBlocks,
  fetchVenueCalendar,
  fetchVenues,
  reactivateVenue,
  removeVenueBlock,
  updateVenue,
} from '@/features/venues/api'
import type { Deactivation, VenueDetails } from '@/features/venues/api'
import { apiRequest } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { refusal, signInAs, signInAsNewAttendee, staffAccount } from './backend'

/**
 * The venue catalogue routes against the real backend (SCRUM-25, SCRUM-67). Only Venue Staff
 * write, so the writes read a Venue Staff account from these variables, which CI sets
 * (frontend.yml), and skip without them on a machine that has none:
 * INTEGRATION_VENUE_STAFF_EMAIL=... INTEGRATION_VENUE_STAFF_PASSWORD=... npm run test:integration
 */
const VENUE_STAFF_EMAIL = import.meta.env.INTEGRATION_VENUE_STAFF_EMAIL ?? ''
const VENUE_STAFF_PASSWORD = import.meta.env.INTEGRATION_VENUE_STAFF_PASSWORD ?? ''
const hasVenueStaff = VENUE_STAFF_EMAIL !== '' && VENUE_STAFF_PASSWORD !== ''

/** An id no database has, so the lookup finds nothing. */
const UNKNOWN_VENUE_ID = 99_999_999

/** A venue this run alone has, so no other test or run can be mistaken for it. */
function uniqueVenue(): VenueDetails {
  return {
    name: `Integration Hall ${Date.now()}-${Math.floor(Math.random() * 1_000_000)}`,
    location: ' Level 2 ',
    capacity: 48,
    facilities: ['Projector', 'Stage'],
    accessibility_features: [],
    supported_layouts: ['theatre'],
    opening_hours: [
      { open: { day: 'friday', time: '18:00' }, close: { day: 'saturday', time: '02:00' } },
      { open: { day: 'monday', time: '09:00' }, close: { day: 'monday', time: '17:00' } },
    ],
  }
}

/** Why the venue is deactivated: what the backend needs since SCRUM-92 (ADR-0053). */
const DEACTIVATION: Deactivation = { category: 'renovation', reason: 'Integration run' }

function signInAsVenueStaff() {
  return signInAs({ email: VENUE_STAFF_EMAIL, password: VENUE_STAFF_PASSWORD })
}

afterEach(() => sendRequestsAs(null))

describe('SCRUM-25 reading the venue catalogue against the backend', () => {
  it('refuses the list without a token (401)', async () => {
    const error = await refusal(fetchVenues())

    expect(error).toMatchObject({ status: 401, code: 'authentication_error' })
  })

  it('lists venues with every field the screens read, active ones only', async () => {
    await signInAs(staffAccount())

    const venues = await fetchVenues()

    for (const venue of venues) {
      expect(venue).toEqual({
        id: expect.any(Number) as unknown,
        name: expect.any(String) as unknown,
        location: expect.any(String) as unknown,
        capacity: expect.any(Number) as unknown,
        facilities: expect.any(Array) as unknown,
        accessibility_features: expect.any(Array) as unknown,
        supported_layouts: expect.any(Array) as unknown,
        opening_hours: expect.any(Array) as unknown,
        setup_minutes: expect.any(Number) as unknown,
        turnaround_minutes: expect.any(Number) as unknown,
        is_active: true,
      })
    }
  })

  it('answers 404 with its message for a venue that does not exist', async () => {
    await signInAs(staffAccount())

    const error = await refusal(fetchVenue(UNKNOWN_VENUE_ID))

    expect(error).toMatchObject({ status: 404, code: 'not_found', message: 'Venue not found.' })
  })
})

describe('SCRUM-25 only Venue Staff change the catalogue (AC4)', () => {
  it('refuses a coordinator adding a venue (403)', async () => {
    await signInAs(staffAccount())

    const error = await refusal(createVenue(uniqueVenue()))

    expect(error).toMatchObject({ status: 403, code: 'authorization_error' })
  })

  it('refuses an attendee changing, deactivating or reactivating a venue (403)', async () => {
    await signInAsNewAttendee()

    // Each call starts only when the one before has been refused, so none rejects unawaited.
    for (const write of [
      () => updateVenue(UNKNOWN_VENUE_ID, uniqueVenue()),
      () => deactivateVenue(UNKNOWN_VENUE_ID, DEACTIVATION),
      () => reactivateVenue(UNKNOWN_VENUE_ID),
    ]) {
      const error = await refusal(write())
      expect(error).toMatchObject({ status: 403, code: 'authorization_error' })
    }
  })

  it('refuses a change without a token (401)', async () => {
    const error = await refusal(updateVenue(UNKNOWN_VENUE_ID, uniqueVenue()))

    expect(error).toMatchObject({ status: 401, code: 'authentication_error' })
  })
})

describe.skipIf(!hasVenueStaff)('SCRUM-25 and SCRUM-67 Venue Staff keep the catalogue', () => {
  it('adds a venue, trimmed and lower-cased, with the standard times and its hours in week order', async () => {
    await signInAsVenueStaff()

    const created = await createVenue(uniqueVenue())

    expect(created).toMatchObject({
      location: 'Level 2',
      capacity: 48,
      facilities: ['projector', 'stage'],
      supported_layouts: ['theatre'],
      setup_minutes: 30,
      turnaround_minutes: 30,
      is_active: true,
    })
    expect(created.opening_hours.map((period) => period.open.day)).toEqual(['monday', 'friday'])
  })

  it('names the fields it refuses, an emptied capacity and an item with a comma among them', async () => {
    await signInAsVenueStaff()

    const error = await refusal(
      createVenue({ ...uniqueVenue(), name: '  ', capacity: null, facilities: ['ok', 'a, b'] }),
    )

    expect(error).toMatchObject({ status: 400, code: 'validation_error' })
    expect(error.fieldErrors).toEqual({
      name: ['Must not be blank.'],
      capacity: ['Field may not be null.'],
      'facilities.1': ['Items cannot contain ",".'],
    })
  })

  it('files an opening-period rule under its close and an overlap under the later period', async () => {
    await signInAsVenueStaff()
    const monday = {
      open: { day: 'monday', time: '09:00' },
      close: { day: 'monday', time: '12:00' },
    } as const

    const badPeriod = await refusal(
      createVenue({
        ...uniqueVenue(),
        opening_hours: [{ ...monday, close: { day: 'monday', time: '08:00' } }],
      }),
    )
    const overlapping = await refusal(
      createVenue({
        ...uniqueVenue(),
        opening_hours: [monday, { ...monday, close: { day: 'monday', time: '13:00' } }],
      }),
    )

    expect(Object.keys(badPeriod.fieldErrors)).toEqual(['opening_hours.0.close'])
    expect(overlapping.fieldErrors).toEqual({ 'opening_hours.1': ['Overlaps opening period 0.'] })
  })

  it('changes a venue, keeping the times it was not sent and reporting no overlaps', async () => {
    await signInAsVenueStaff()
    const created = await createVenue(uniqueVenue())

    const changed = await updateVenue(created.id, { ...uniqueVenue(), capacity: 60 })

    expect(changed).toMatchObject({
      id: created.id,
      capacity: 60,
      setup_minutes: 30,
      overlap_warnings: [],
      block_overlap_warnings: [],
    })
  })

  it('deactivates a venue, which leaves the list but still opens, and reactivates it', async () => {
    await signInAsVenueStaff()
    const created = await createVenue(uniqueVenue())

    const deactivated = await deactivateVenue(created.id, DEACTIVATION)
    const listedWhileOff = await fetchVenues()
    const stillOpens = await fetchVenue(created.id)
    const reactivated = await reactivateVenue(created.id)
    const listedAgain = await fetchVenues()

    expect(deactivated.is_active).toBe(false)
    expect(listedWhileOff.map((venue) => venue.id)).not.toContain(created.id)
    expect(stillOpens.is_active).toBe(false)
    expect(reactivated.is_active).toBe(true)
    expect(listedAgain.map((venue) => venue.id)).toContain(created.id)
  })

  it('refuses a deactivation with nothing chosen and a blank note, naming each field', async () => {
    await signInAsVenueStaff()
    const created = await createVenue(uniqueVenue())

    const error = await refusal(deactivateVenue(created.id, { category: '', reason: '   ' }))

    expect(error).toMatchObject({ status: 400, code: 'validation_error' })
    expect(error.fieldErrors).toEqual({
      category: [
        'Category must be one of maintenance, equipment_failure, renovation, safety_concern or other.',
      ],
      reason: ['Must not be blank.'],
    })
    await expect(fetchVenue(created.id)).resolves.toMatchObject({ is_active: true })
  })

  it('refuses a deactivation without a category and a note before looking for the venue', async () => {
    await signInAsVenueStaff()

    const error = await refusal(
      apiRequest(`/api/venues/${UNKNOWN_VENUE_ID}/deactivate`, { method: 'POST', body: {} }),
    )

    expect(error).toMatchObject({ status: 400, code: 'validation_error' })
    expect(error.fieldErrors).toEqual({
      category: ['Missing data for required field.'],
      reason: ['Missing data for required field.'],
    })
  })

  it.todo('reports bookings a longer turnaround now overlaps (needs seeded confirmed bookings)')
})

/** A whole business day far enough ahead that no "before today" rule refuses it. */
const FUTURE_DAY = { range_start: '2099-03-02T00:00:00', range_end: '2099-03-03T00:00:00' }
const FUTURE_BLOCK = {
  start_time: '2099-03-02T10:00',
  end_time: '2099-03-02T12:00',
  category: 'renovation',
  reason: '  Integration maintenance  ',
}

describe('SCRUM-26 a venue calendar against the backend', () => {
  it('refuses the calendar without a token (401)', async () => {
    const error = await refusal(fetchVenueCalendar(UNKNOWN_VENUE_ID, FUTURE_DAY))

    expect(error).toMatchObject({ status: 401, code: 'authentication_error' })
  })

  it('refuses an attendee the calendar (403, AC4)', async () => {
    await signInAsNewAttendee()

    const error = await refusal(fetchVenueCalendar(UNKNOWN_VENUE_ID, FUTURE_DAY))

    expect(error).toMatchObject({ status: 403, code: 'authorization_error' })
  })

  it('files a range that ends where it starts under range_end', async () => {
    await signInAs(staffAccount())

    const error = await refusal(
      fetchVenueCalendar(UNKNOWN_VENUE_ID, { ...FUTURE_DAY, range_end: FUTURE_DAY.range_start }),
    )

    expect(error).toMatchObject({ status: 400, code: 'validation_error' })
    expect(error.fieldErrors).toEqual({ range_end: ['range_end must be after range_start.'] })
  })

  it('answers 404 for a venue that does not exist once the range is valid', async () => {
    await signInAs(staffAccount())

    const error = await refusal(fetchVenueCalendar(UNKNOWN_VENUE_ID, FUTURE_DAY))

    expect(error).toMatchObject({ status: 404, message: 'Venue not found.' })
  })
})

describe('SCRUM-34 only Venue Staff see and change blocks', () => {
  it('refuses blocks without a token (401)', async () => {
    const error = await refusal(fetchVenueBlocks(UNKNOWN_VENUE_ID))

    expect(error).toMatchObject({ status: 401, code: 'authentication_error' })
  })

  it('refuses a coordinator listing, adding or removing blocks (403)', async () => {
    await signInAs(staffAccount())

    // Each call starts only when the one before has been refused, so none rejects unawaited.
    for (const call of [
      () => fetchVenueBlocks(UNKNOWN_VENUE_ID),
      () => blockVenue(UNKNOWN_VENUE_ID, FUTURE_BLOCK),
      () => removeVenueBlock(UNKNOWN_VENUE_ID, UNKNOWN_VENUE_ID),
    ]) {
      const error = await refusal(call())
      expect(error).toMatchObject({ status: 403, code: 'authorization_error' })
    }
  })
})

describe.skipIf(!hasVenueStaff)('SCRUM-34 and SCRUM-26 Venue Staff block a venue', () => {
  it('blocks a venue, which its calendar then shows to each role as it may be told, then removes it', async () => {
    await signInAsVenueStaff()
    const venue = await createVenue(uniqueVenue())

    const created = await blockVenue(venue.id, FUTURE_BLOCK)
    const listed = await fetchVenueBlocks(venue.id)
    const staffCalendar = await fetchVenueCalendar(venue.id, FUTURE_DAY)
    await signInAs(staffAccount())
    const coordinatorCalendar = await fetchVenueCalendar(venue.id, FUTURE_DAY)
    await signInAsVenueStaff()
    await removeVenueBlock(venue.id, created.id)
    const afterRemoval = await fetchVenueCalendar(venue.id, FUTURE_DAY)

    expect(created).toMatchObject({
      venue_id: venue.id,
      start_time: '2099-03-02T10:00:00+08:00',
      end_time: '2099-03-02T12:00:00+08:00',
      category: 'renovation',
      reason: 'Integration maintenance',
      conflicting_bookings: [],
    })
    expect(listed.map((block) => [block.id, block.category])).toEqual([[created.id, 'renovation']])
    expect(staffCalendar).toEqual([
      {
        start_time: '2099-03-02T10:00:00+08:00',
        end_time: '2099-03-02T12:00:00+08:00',
        event_start: null,
        event_end: null,
        kind: 'block',
        reason: 'Integration maintenance',
      },
    ])
    expect(coordinatorCalendar.map((entry) => entry.reason)).toEqual(['maintenance'])
    expect(afterRemoval).toEqual([])
  })

  it('refuses a block that ended before today, a blank reason and an unknown category, by field', async () => {
    await signInAsVenueStaff()
    const venue = await createVenue(uniqueVenue())

    const past = await refusal(
      blockVenue(venue.id, {
        ...FUTURE_BLOCK,
        start_time: '2000-01-01T09:00',
        end_time: '2000-01-01T10:00',
      }),
    )
    const blank = await refusal(blockVenue(venue.id, { ...FUTURE_BLOCK, reason: '   ' }))
    const unknownCategory = await refusal(
      blockVenue(venue.id, { ...FUTURE_BLOCK, category: 'flood' }),
    )

    expect(past.fieldErrors).toEqual({ end_time: ['Block cannot end before today.'] })
    expect(blank.fieldErrors).toEqual({ reason: ['Must not be blank.'] })
    expect(unknownCategory.fieldErrors).toEqual({
      category: [
        'Category must be one of maintenance, equipment_failure, renovation, safety_concern or other.',
      ],
    })
  })

  it('answers 404 for a block that belongs to another venue', async () => {
    await signInAsVenueStaff()
    const blocked = await createVenue(uniqueVenue())
    const other = await createVenue(uniqueVenue())
    const block = await blockVenue(blocked.id, FUTURE_BLOCK)

    const error = await refusal(removeVenueBlock(other.id, block.id))

    expect(error).toMatchObject({ status: 404, message: 'Block not found.' })
  })

  it.todo('lists the confirmed bookings a block cuts into (needs seeded confirmed bookings)')
})
