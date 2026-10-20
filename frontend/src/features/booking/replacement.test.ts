import { MOCK_ARRANGEMENTS } from '@/mocks/handlers/bookingFixtures'

import { findAnotherVenuePath, readReplacementRequest } from './replacement'

const { bookedHall } = MOCK_ARRANGEMENTS

/** The venue search's parameters in the path, as name and value pairs. */
function paramsOf(path: string): Record<string, string> {
  return Object.fromEntries(new URL(path, 'http://localhost').searchParams)
}

describe('SCRUM-92 finding another venue for a flagged arrangement', () => {
  it('sets the search to the arrangement’s period and occupancy, naming what it replaces', () => {
    const path = findAnotherVenuePath('EVR-BOOK0107', bookedHall)

    expect(path.startsWith('/staff/venue-search?')).toBe(true)
    expect(paramsOf(path)).toEqual({
      event: 'EVR-BOOK0107',
      replaces: String(bookedHall.id),
      instead_of: String(bookedHall.venue_id),
      date: '2026-11-26',
      start: '13:00',
      end: '17:00',
      min_capacity: '10',
    })
  })

  it('carries the layout, and the end date of an arrangement that ends on a later day', () => {
    const overnight = {
      ...bookedHall,
      ends_at: '2026-11-27T01:00:00+08:00',
      required_layout: 'theatre',
    }

    expect(paramsOf(findAnotherVenuePath('EVR-BOOK0107', overnight))).toMatchObject({
      end: '01:00',
      end_date: '2026-11-27',
      required_layout: 'theatre',
    })
  })
})

describe('SCRUM-92 the replacement the request form is raising', () => {
  it('reads the arrangement to replace and the venue chosen from the URL', () => {
    expect(readReplacementRequest(new URLSearchParams('replaces=9104&venue=2'))).toEqual({
      arrangementId: 9104,
      venueId: '2',
    })
  })

  it('leaves the venue empty when none was chosen', () => {
    expect(readReplacementRequest(new URLSearchParams('replaces=9104'))).toEqual({
      arrangementId: 9104,
      venueId: '',
    })
  })

  it.each(['', 'venue=2', 'replaces=abc&venue=2'])('reads no replacement from %j', (query) => {
    expect(readReplacementRequest(new URLSearchParams(query))).toBeNull()
  })
})
