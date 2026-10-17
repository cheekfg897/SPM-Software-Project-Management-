import { searchVenues } from '@/features/venueSearch/api'
import type { VenueSearchRequest } from '@/features/venueSearch/api'
import { apiRequest } from '@/lib/api'
import { refusalOf } from '@/test/refusalOf'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { MOCK_ACCOUNTS, mockTokenFor } from '../fixtures/accounts'

import { MOCK_SEARCH_VENUES } from './venueSearchFixtures'

/**
 * The venue search mock stands in for `POST /api/venues/search` (SCRUM-35), so these tests pin
 * it to what backend/app/modules/venue/routes.py and services.search_venues answer.
 */

const NO_MATCHES_MESSAGE = 'No venues match your search criteria.'

/** 20 November, 09:00 to 17:00: every active venue is free then. */
function search(overrides: Partial<VenueSearchRequest> = {}): VenueSearchRequest {
  return {
    start_time: '2026-11-20T09:00:00+08:00',
    end_time: '2026-11-20T17:00:00+08:00',
    min_capacity: 1,
    location: null,
    required_layout: null,
    required_facilities: [],
    required_accessibility: [],
    ...overrides,
  }
}

async function namesFound(overrides: Partial<VenueSearchRequest> = {}): Promise<string[]> {
  const { results } = await searchVenues(search(overrides))
  return results.map((venue) => venue.name)
}

/** Why the search was refused. Takes any body, not only a well-formed one. */
function searchRefusal(body: unknown) {
  return refusalOf(apiRequest('/api/venues/search', { method: 'POST', body }))
}

beforeEach(() => {
  sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.coordinator))
})

describe('SCRUM-35 venue search mock: who may search', () => {
  it('refuses a request without a token (401)', async () => {
    sendRequestsAs(null)

    expect(await searchRefusal(search())).toMatchObject({ status: 401 })
  })

  it.each([
    ['an attendee', MOCK_ACCOUNTS.attendee],
    ['Venue Staff', MOCK_ACCOUNTS.venueStaff],
  ])('refuses %s (403): search is for Event Coordinators', async (_who, account) => {
    sendRequestsAs(mockTokenFor(account))

    expect(await searchRefusal(search())).toMatchObject({ status: 403 })
  })
})

describe('SCRUM-35 venue search mock: what it finds', () => {
  it('returns every active venue that is free, ordered by name, without a message', async () => {
    const body = await searchVenues(search())

    expect(body.results.map((venue) => venue.name)).toEqual([
      'Boardroom Five',
      'Garden Pavilion',
      'Harbourfront Hall',
      'Orchid Room',
    ])
    expect(body).not.toHaveProperty('message')
  })

  it('shows each venue with its capacity, location and the requirements it meets', async () => {
    const { results } = await searchVenues(
      search({
        required_layout: 'theatre',
        required_facilities: [' Projector ', 'STAGE'],
        required_accessibility: ['Hearing Loop'],
      }),
    )

    expect(results).toEqual([
      {
        id: MOCK_SEARCH_VENUES.harbourfrontHall.id,
        name: 'Harbourfront Hall',
        capacity: 300,
        location: 'Marina Bay, Level 1',
        matched_requirements: {
          facilities: ['projector', 'stage'],
          accessibility_features: ['hearing loop'],
          layout: 'theatre',
        },
      },
    ])
  })

  it('keeps a venue whose capacity is exactly the minimum, and drops one a seat short', async () => {
    expect(await namesFound({ min_capacity: 150 })).toEqual([
      'Garden Pavilion',
      'Harbourfront Hall',
    ])
    expect(await namesFound({ min_capacity: 151 })).toEqual(['Harbourfront Hall'])
  })

  it('matches any venue whose location contains the text, whatever its case', async () => {
    expect(await namesFound({ location: 'marina' })).toEqual(['Harbourfront Hall', 'Orchid Room'])
  })

  it('treats a blank location as anywhere', async () => {
    expect(await namesFound({ location: '   ' })).toHaveLength(4)
  })

  it.each([
    ['a facility', { required_facilities: ['whiteboard'] }, ['Orchid Room']],
    [
      'an accessibility need',
      { required_accessibility: ['step-free access'] },
      ['Garden Pavilion', 'Harbourfront Hall'],
    ],
    ['a layout', { required_layout: 'boardroom' }, ['Boardroom Five', 'Orchid Room']],
  ])('leaves out a venue that lacks %s', async (_what, overrides, expected) => {
    expect(await namesFound(overrides)).toEqual(expected)
  })

  it.each([
    ['classroom', ['Orchid Room']],
    ['theatre', ['Harbourfront Hall']],
    ['boardroom', ['Boardroom Five', 'Orchid Room']],
    ['banquet', ['Garden Pavilion', 'Harbourfront Hall']],
    ['exhibition', ['Harbourfront Hall']],
    ['other', ['Garden Pavilion']],
  ])('finds the venues supporting the %s layout', async (layout, expected) => {
    expect(await namesFound({ required_layout: layout })).toEqual(expected)
  })

  it('answers an empty list with the backend message when nothing matches', async () => {
    const body = await searchVenues(search({ min_capacity: 1000 }))

    expect(body).toEqual({ results: [], message: NO_MATCHES_MESSAGE })
  })
})

describe('SCRUM-35 venue search mock: who is free', () => {
  const BOOKED_DAY = '2026-11-21'

  function on(day: string, from: string, to: string): Partial<VenueSearchRequest> {
    return { start_time: `${day}T${from}:00+08:00`, end_time: `${day}T${to}:00+08:00` }
  }

  it('leaves out a venue booked during the period', async () => {
    expect(await namesFound(on(BOOKED_DAY, '11:00', '12:00'))).not.toContain('Garden Pavilion')
  })

  it.each([
    ['ends within setup plus turnaround before the booking', '07:00', '08:31'],
    ['starts within setup plus turnaround after it', '15:29', '18:00'],
  ])('leaves out a venue when the event %s', async (_when, from, to) => {
    expect(await namesFound(on(BOOKED_DAY, from, to))).not.toContain('Garden Pavilion')
  })

  it.each([
    ['ends setup plus turnaround before the booking', '07:00', '08:30'],
    ['starts setup plus turnaround after it', '15:30', '18:00'],
  ])('keeps a venue when the event %s', async (_when, from, to) => {
    expect(await namesFound(on(BOOKED_DAY, from, to))).toContain('Garden Pavilion')
  })

  it('keeps a venue whose only booking then was cancelled', async () => {
    expect(await namesFound(on('2026-11-20', '10:00', '11:00'))).toContain('Harbourfront Hall')
  })

  it('leaves out a venue blocked during the period, but not one blocked only until it starts', async () => {
    expect(await namesFound(on('2026-11-22', '17:00', '19:00'))).not.toContain('Boardroom Five')
    expect(await namesFound(on('2026-11-22', '18:00', '19:00'))).toContain('Boardroom Five')
  })
})

describe('SCRUM-35 venue search mock: refusing a search (400)', () => {
  it('names each required field left out', async () => {
    const error = await searchRefusal({})

    expect(error).toMatchObject({ status: 400, code: 'validation_error' })
    expect(error.fieldErrors).toEqual({
      start_time: ['Missing data for required field.'],
      end_time: ['Missing data for required field.'],
      min_capacity: ['Missing data for required field.'],
    })
  })

  it.each([
    ['ends before it starts', '2026-11-20T08:00:00+08:00'],
    ['ends as it starts', '2026-11-20T09:00:00+08:00'],
  ])('refuses a period that %s, under the end time', async (_how, endTime) => {
    const error = await searchRefusal(search({ end_time: endTime }))

    expect(error.fieldErrors).toEqual({ end_time: ['end_time must be after start_time.'] })
  })

  it('refuses a minimum capacity under 1', async () => {
    const error = await searchRefusal(search({ min_capacity: 0 }))

    expect(error.fieldErrors).toEqual({ min_capacity: ['min_capacity must be a positive number.'] })
  })

  it('refuses a layout the backend does not know', async () => {
    const error = await searchRefusal(search({ required_layout: 'cabaret' }))

    expect(error.fieldErrors).toEqual({
      required_layout: [
        'Must be one of: classroom, theatre, boardroom, banquet, exhibition, other.',
      ],
    })
  })

  it('names each bad item by its place in the list', async () => {
    const error = await searchRefusal(
      search({
        required_facilities: ['projector', 'tables, chairs', 'x'.repeat(51)],
        required_accessibility: ['  '],
      }),
    )

    expect(error.fieldErrors).toEqual({
      'required_facilities.1': ['Items cannot contain ",".'],
      'required_facilities.2': ['Items must be at most 50 characters.'],
      'required_accessibility.0': ['Items cannot be blank.'],
    })
  })

  it('accepts an item of exactly the longest length', async () => {
    const body = await searchVenues(search({ required_facilities: ['x'.repeat(50)] }))

    expect(body.results).toEqual([])
  })

  it('refuses more items than a venue can store', async () => {
    const tenItems = Array.from({ length: 10 }, (_, index) => `item ${index}`)

    const error = await searchRefusal(search({ required_facilities: tenItems }))

    expect(error.fieldErrors).toEqual({ required_facilities: ['At most 9 items are allowed.'] })
  })
})
