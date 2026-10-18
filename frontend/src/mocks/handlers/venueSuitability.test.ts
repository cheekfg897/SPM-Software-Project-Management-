import { checkSuitability, fetchVenues } from '@/features/venueSearch/api'
import type { SuitabilityRequest } from '@/features/venueSearch/api'
import { apiRequest } from '@/lib/api'
import { refusalOf } from '@/test/refusalOf'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { MOCK_ACCOUNTS, mockTokenFor } from '../fixtures/accounts'

import { MOCK_VENUES } from './venueFixtures'

/**
 * The venue list and the suitability check, as the venue search page reads them (SCRUM-36),
 * pinned to what backend/app/modules/venue/routes.py and services.py answer.
 */

const ORCHID_ROOM = MOCK_VENUES.orchidRoom
const HARBOURFRONT_HALL = MOCK_VENUES.harbourfrontHall
/** An id no mock venue has. */
const UNKNOWN_VENUE_ID = 999

function needs(overrides: Partial<SuitabilityRequest> = {}): SuitabilityRequest {
  return {
    expected_attendance: 50,
    required_layout: null,
    required_facilities: [],
    required_accessibility: [],
    ...overrides,
  }
}

beforeEach(() => {
  sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.coordinator))
})

describe('SCRUM-36 venue list mock', () => {
  it('refuses a request without a token (401)', async () => {
    sendRequestsAs(null)

    expect(await refusalOf(fetchVenues())).toMatchObject({ status: 401 })
  })

  it('lists the active venues by name to anyone signed in', async () => {
    sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.attendee))

    const venues = await fetchVenues()

    expect(venues.map((venue) => venue.name)).toEqual([
      'Boardroom Five',
      'Boardroom Two',
      'Garden Pavilion',
      'Harbourfront Hall',
      'Lawn Marquee',
      'Marina Hall',
      'Orchid Room',
    ])
    expect(venues[3]).toEqual(HARBOURFRONT_HALL)
  })
})

describe('SCRUM-36 suitability mock: who may check', () => {
  it('refuses a request without a token (401)', async () => {
    sendRequestsAs(null)

    const error = await refusalOf(checkSuitability(ORCHID_ROOM.id, needs()))

    expect(error).toMatchObject({ status: 401 })
  })

  it('refuses an attendee (403)', async () => {
    sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.attendee))

    const error = await refusalOf(checkSuitability(ORCHID_ROOM.id, needs()))

    expect(error).toMatchObject({ status: 403 })
  })

  it.each([
    ['an Event Coordinator', MOCK_ACCOUNTS.coordinator],
    ['Venue Staff', MOCK_ACCOUNTS.venueStaff],
  ])('answers %s', async (_who, account) => {
    sendRequestsAs(mockTokenFor(account))

    expect(await checkSuitability(ORCHID_ROOM.id, needs())).toEqual({
      suitable: true,
      reasons: [],
    })
  })
})

describe('SCRUM-36 suitability mock: the answer', () => {
  it('names capacity when the attendance is more than the venue holds (AC1)', async () => {
    const result = await checkSuitability(ORCHID_ROOM.id, needs({ expected_attendance: 150 }))

    expect(result).toEqual({
      suitable: false,
      reasons: [
        {
          requirement: 'capacity',
          message: "Expected attendance of 150 exceeds the venue's capacity of 100.",
        },
      ],
    })
  })

  it('is suitable at exactly the venue capacity', async () => {
    const result = await checkSuitability(ORCHID_ROOM.id, needs({ expected_attendance: 100 }))

    expect(result.suitable).toBe(true)
  })

  it('names the missing accessibility requirement (AC2)', async () => {
    const result = await checkSuitability(
      ORCHID_ROOM.id,
      needs({ required_accessibility: ['Step-free access'] }),
    )

    expect(result).toEqual({
      suitable: false,
      reasons: [
        { requirement: 'accessibility', message: 'The venue does not offer step-free access.' },
      ],
    })
  })

  it('lists every failure: capacity, then facilities, accessibility and layout', async () => {
    const result = await checkSuitability(
      ORCHID_ROOM.id,
      needs({
        expected_attendance: 101,
        required_layout: 'theatre',
        required_facilities: ['stage', 'projector', 'pa system'],
        required_accessibility: ['hearing loop'],
      }),
    )

    expect(result.reasons).toEqual([
      {
        requirement: 'capacity',
        message: "Expected attendance of 101 exceeds the venue's capacity of 100.",
      },
      { requirement: 'facilities', message: 'The venue does not offer stage.' },
      { requirement: 'facilities', message: 'The venue does not offer pa system.' },
      { requirement: 'accessibility', message: 'The venue does not offer hearing loop.' },
      { requirement: 'layout', message: 'The venue does not support the theatre layout.' },
    ])
  })

  it('is suitable when the venue meets every requirement (AC3)', async () => {
    const result = await checkSuitability(
      HARBOURFRONT_HALL.id,
      needs({
        expected_attendance: 300,
        required_layout: 'banquet',
        required_facilities: ['Stage'],
        required_accessibility: ['step-free access'],
      }),
    )

    expect(result).toEqual({ suitable: true, reasons: [] })
  })

  it('checks a deactivated venue too, as the backend describes any venue by id', async () => {
    const result = await checkSuitability(MOCK_VENUES.archiveStudio.id, needs())

    expect(result.suitable).toBe(true)
  })

  it('answers 404 for a venue that does not exist', async () => {
    const error = await refusalOf(checkSuitability(UNKNOWN_VENUE_ID, needs()))

    expect(error).toMatchObject({ status: 404, code: 'not_found', message: 'Venue not found.' })
  })

  it('refuses a missing or non-positive attendance before looking for the venue (400)', async () => {
    const missing = await refusalOf(
      apiRequest(`/api/venues/${UNKNOWN_VENUE_ID}/suitability`, { method: 'POST', body: {} }),
    )
    const zero = await refusalOf(
      checkSuitability(ORCHID_ROOM.id, needs({ expected_attendance: 0 })),
    )

    expect(missing.fieldErrors).toEqual({
      expected_attendance: ['Missing data for required field.'],
    })
    expect(zero.fieldErrors).toEqual({
      expected_attendance: ['expected_attendance must be a positive number.'],
    })
  })

  it('refuses a bad requirement item the way search does', async () => {
    const error = await refusalOf(
      checkSuitability(ORCHID_ROOM.id, needs({ required_accessibility: ['ramp, lift'] })),
    )

    expect(error.fieldErrors).toEqual({ 'required_accessibility.0': ['Items cannot contain ",".'] })
  })
})
