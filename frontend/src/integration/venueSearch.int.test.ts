import { checkSuitability, fetchVenues, searchVenues } from '@/features/venueSearch/api'
import type { SuitabilityRequest, VenueSearchRequest } from '@/features/venueSearch/api'
import { apiRequest } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { refusal, signInAs, signInAsNewAttendee, staffAccount } from './backend'

/**
 * Venue search (SCRUM-35) and the suitability check (SCRUM-36) against the real backend. Only
 * Venue Staff create venues, and CI seeds no Venue Staff account yet, so the checks that need a
 * venue of their own read one from these variables and skip without them:
 * INTEGRATION_VENUE_STAFF_EMAIL=... INTEGRATION_VENUE_STAFF_PASSWORD=... npm run test:integration
 */
const VENUE_STAFF_EMAIL = import.meta.env.INTEGRATION_VENUE_STAFF_EMAIL ?? ''
const VENUE_STAFF_PASSWORD = import.meta.env.INTEGRATION_VENUE_STAFF_PASSWORD ?? ''
const hasVenueStaff = VENUE_STAFF_EMAIL !== '' && VENUE_STAFF_PASSWORD !== ''

const NO_MATCHES_MESSAGE = 'No venues match your search criteria.'
/** An id no database has, so the lookup finds nothing. */
const UNKNOWN_VENUE_ID = 99_999_999

/** Text no other test or run uses, to keep this run's venue apart. */
function uniqueText(label: string): string {
  return `${label} ${Date.now()}-${Math.floor(Math.random() * 1_000_000)}`
}

function search(overrides: Partial<VenueSearchRequest> = {}): VenueSearchRequest {
  return {
    start_time: '2027-03-10T09:00:00+08:00',
    end_time: '2027-03-10T17:00:00+08:00',
    min_capacity: 1,
    location: null,
    required_layout: null,
    required_facilities: [],
    required_accessibility: [],
    ...overrides,
  }
}

function needs(overrides: Partial<SuitabilityRequest> = {}): SuitabilityRequest {
  return {
    expected_attendance: 1,
    required_layout: null,
    required_facilities: [],
    required_accessibility: [],
    ...overrides,
  }
}

function signInAsCoordinator() {
  return signInAs(staffAccount())
}

interface SeededVenue {
  id: number
  location: string
}

/**
 * A venue of this run's own, made by Venue Staff: 100 seats, a projector, step-free access and
 * the theatre layout, at a location nothing else has. Then signs in as the coordinator.
 */
async function seedVenue(): Promise<SeededVenue> {
  await signInAs({ email: VENUE_STAFF_EMAIL, password: VENUE_STAFF_PASSWORD })
  const location = uniqueText('Search Street')
  const venue = await apiRequest<SeededVenue>('/api/venues', {
    method: 'POST',
    body: {
      name: uniqueText('Integration Search Hall'),
      location,
      capacity: 100,
      facilities: ['Projector'],
      accessibility_features: ['Step-free access'],
      supported_layouts: ['theatre'],
    },
  })
  await signInAsCoordinator()
  return venue
}

afterEach(() => sendRequestsAs(null))

describe('SCRUM-35 venue search against the backend', () => {
  it('refuses a search without a token (401)', async () => {
    const error = await refusal(searchVenues(search()))

    expect(error).toMatchObject({ status: 401, code: 'authentication_error' })
  })

  it('refuses a role other than the Event Coordinator (403)', async () => {
    await signInAsNewAttendee()

    const error = await refusal(searchVenues(search()))

    expect(error).toMatchObject({ status: 403, code: 'authorization_error' })
  })

  it('names the end time when the period ends before it starts (400)', async () => {
    await signInAsCoordinator()

    const error = await refusal(searchVenues(search({ end_time: '2027-03-10T08:00:00+08:00' })))

    expect(error).toMatchObject({ status: 400, code: 'validation_error' })
    expect(error.fieldErrors).toEqual({ end_time: ['end_time must be after start_time.'] })
  })

  it('names a bad requirement item by its place in the list (400)', async () => {
    await signInAsCoordinator()

    const error = await refusal(
      searchVenues(search({ required_facilities: ['projector', 'tables, chairs'] })),
    )

    expect(error.fieldErrors).toEqual({ 'required_facilities.1': ['Items cannot contain ",".'] })
  })

  it('answers an empty list with its message when nothing matches', async () => {
    await signInAsCoordinator()

    const body = await searchVenues(search({ location: uniqueText('Nowhere') }))

    expect(body).toEqual({ results: [], message: NO_MATCHES_MESSAGE })
  })

  it.skipIf(!hasVenueStaff)(
    'finds a free venue with its capacity, location and the requirements it meets',
    async () => {
      const venue = await seedVenue()

      const body = await searchVenues(
        search({
          min_capacity: 100,
          location: venue.location,
          required_layout: 'theatre',
          required_facilities: [' PROJECTOR '],
          required_accessibility: ['Step-free access'],
        }),
      )

      expect(body).toEqual({
        results: [
          {
            id: venue.id,
            name: expect.stringContaining('Integration Search Hall') as unknown,
            capacity: 100,
            location: venue.location,
            matched_requirements: {
              facilities: ['projector'],
              accessibility_features: ['step-free access'],
              layout: 'theatre',
            },
          },
        ],
      })
    },
  )

  it.skipIf(!hasVenueStaff)('leaves out a venue a seat short of the minimum', async () => {
    const venue = await seedVenue()

    const body = await searchVenues(search({ min_capacity: 101, location: venue.location }))

    expect(body.results).toEqual([])
  })
})

describe('SCRUM-36 checking a venue against the backend', () => {
  it('refuses a check without a token (401)', async () => {
    const error = await refusal(checkSuitability(UNKNOWN_VENUE_ID, needs()))

    expect(error).toMatchObject({ status: 401, code: 'authentication_error' })
  })

  it('refuses an attendee (403)', async () => {
    await signInAsNewAttendee()

    const error = await refusal(checkSuitability(UNKNOWN_VENUE_ID, needs()))

    expect(error).toMatchObject({ status: 403, code: 'authorization_error' })
  })

  it('answers 404 with its message for a venue that does not exist', async () => {
    await signInAsCoordinator()

    const error = await refusal(checkSuitability(UNKNOWN_VENUE_ID, needs()))

    expect(error).toMatchObject({ status: 404, code: 'not_found', message: 'Venue not found.' })
  })

  it('names the attendance when it is not a positive number (400)', async () => {
    await signInAsCoordinator()

    const error = await refusal(
      checkSuitability(UNKNOWN_VENUE_ID, needs({ expected_attendance: 0 })),
    )

    expect(error.fieldErrors).toEqual({
      expected_attendance: ['expected_attendance must be a positive number.'],
    })
  })

  it('lists the venues to choose from with the fields the picker reads', async () => {
    await signInAsCoordinator()

    const venues = await fetchVenues()

    for (const venue of venues) {
      expect(venue).toMatchObject({
        id: expect.any(Number) as unknown,
        name: expect.any(String) as unknown,
        location: expect.any(String) as unknown,
        capacity: expect.any(Number) as unknown,
      })
    }
  })

  it.skipIf(!hasVenueStaff)('names capacity and the missing requirement (AC1, AC2)', async () => {
    const venue = await seedVenue()

    const result = await checkSuitability(
      venue.id,
      needs({ expected_attendance: 150, required_accessibility: ['Hearing loop'] }),
    )

    expect(result).toEqual({
      suitable: false,
      reasons: [
        {
          requirement: 'capacity',
          message: "Expected attendance of 150 exceeds the venue's capacity of 100.",
        },
        { requirement: 'accessibility', message: 'The venue does not offer hearing loop.' },
      ],
    })
  })

  it.skipIf(!hasVenueStaff)('says suitable when every requirement is met (AC3)', async () => {
    const venue = await seedVenue()

    const result = await checkSuitability(
      venue.id,
      needs({
        expected_attendance: 100,
        required_layout: 'theatre',
        required_facilities: ['projector'],
        required_accessibility: ['step-free access'],
      }),
    )

    expect(result).toEqual({ suitable: true, reasons: [] })
  })

  it.skipIf(!hasVenueStaff)('lists a new venue among those to choose from', async () => {
    const venue = await seedVenue()

    const venues = await fetchVenues()

    expect(venues.map((listed) => listed.id)).toContain(venue.id)
  })
})
