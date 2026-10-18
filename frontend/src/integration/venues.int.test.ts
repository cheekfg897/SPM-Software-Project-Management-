import {
  createVenue,
  deactivateVenue,
  fetchVenue,
  fetchVenues,
  reactivateVenue,
  updateVenue,
} from '@/features/venues/api'
import type { VenueDetails } from '@/features/venues/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { refusal, signInAs, signInAsNewAttendee, staffAccount } from './backend'

/**
 * The venue catalogue routes against the real backend (SCRUM-25, SCRUM-67). Only Venue Staff
 * write, and CI seeds no Venue Staff account, so the writes that need one read it from these
 * variables and skip without them:
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
      () => deactivateVenue(UNKNOWN_VENUE_ID),
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

    const deactivated = await deactivateVenue(created.id)
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

  it.todo('reports bookings a longer turnaround now overlaps (needs seeded confirmed bookings)')
})
