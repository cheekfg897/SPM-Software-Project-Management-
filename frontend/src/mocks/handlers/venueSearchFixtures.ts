/**
 * The venues the venue search mock knows (SCRUM-35, SCRUM-36), with the bookings and blocks
 * that make some of them busy. Shared with the e2e journeys, so: relative imports, no msw.
 */

/** A venue as `GET /api/venues/<id>` returns it (VenueSchema in venue/schemas.py). */
export interface MockSearchVenue {
  id: number
  name: string
  location: string
  capacity: number
  /** Stored trimmed and lower case, as the backend normalises them. */
  facilities: readonly string[]
  accessibility_features: readonly string[]
  supported_layouts: readonly string[]
  /** Left empty: search and the suitability check don't read opening hours. */
  opening_hours: readonly unknown[]
  setup_minutes: number
  turnaround_minutes: number
  is_active: boolean
}

/** A period the venue is taken: a booking (padded by setup and turnaround) or a block (not). */
export interface MockVenuePeriod {
  venue_id: number
  start_time: string
  end_time: string
}

/** A booking holds its venue unless it was cancelled. */
export interface MockVenueBooking extends MockVenuePeriod {
  status: 'tentative' | 'confirmed' | 'cancelled'
}

const HARBOURFRONT_HALL: MockSearchVenue = {
  id: 31,
  name: 'Harbourfront Hall',
  location: 'Marina Bay, Level 1',
  capacity: 300,
  facilities: ['projector', 'stage', 'pa system'],
  accessibility_features: ['step-free access', 'hearing loop'],
  supported_layouts: ['theatre', 'banquet', 'exhibition'],
  opening_hours: [],
  setup_minutes: 30,
  turnaround_minutes: 30,
  is_active: true,
}

/**
 * Saved out of name order, as the backend sorts its answer by name. The Archive Studio is
 * deactivated and would match everything, so a search or list that forgot `is_active` shows it.
 */
export const MOCK_SEARCH_VENUES = {
  orchidRoom: {
    ...HARBOURFRONT_HALL,
    id: 32,
    name: 'Orchid Room',
    location: 'Marina Bay, Level 3',
    capacity: 100,
    facilities: ['projector', 'whiteboard'],
    accessibility_features: [],
    supported_layouts: ['classroom', 'boardroom'],
  },
  harbourfrontHall: HARBOURFRONT_HALL,
  gardenPavilion: {
    ...HARBOURFRONT_HALL,
    id: 33,
    name: 'Garden Pavilion',
    location: 'Sentosa',
    capacity: 150,
    facilities: ['pa system'],
    accessibility_features: ['step-free access'],
    supported_layouts: ['banquet', 'other'],
    setup_minutes: 60,
  },
  archiveStudio: {
    ...HARBOURFRONT_HALL,
    id: 34,
    name: 'Archive Studio',
    location: 'Marina Bay, Basement',
    capacity: 500,
    is_active: false,
  },
  boardroomFive: {
    ...HARBOURFRONT_HALL,
    id: 35,
    name: 'Boardroom Five',
    location: 'Tanjong Pagar',
    capacity: 20,
    facilities: ['screen'],
    accessibility_features: [],
    supported_layouts: ['boardroom'],
  },
} as const satisfies Record<string, MockSearchVenue>

/**
 * The Garden Pavilion is booked on 21 November, 10:00 to 14:00. With its 60 minutes' setup and
 * 30 minutes' turnaround, an event there must end by 08:30 or start from 15:30. The Harbourfront
 * Hall's booking on 20 November was cancelled, so it doesn't hold the venue.
 */
export const MOCK_VENUE_BOOKINGS: readonly MockVenueBooking[] = [
  {
    venue_id: MOCK_SEARCH_VENUES.gardenPavilion.id,
    start_time: '2026-11-21T10:00:00+08:00',
    end_time: '2026-11-21T14:00:00+08:00',
    status: 'confirmed',
  },
  {
    venue_id: MOCK_SEARCH_VENUES.harbourfrontHall.id,
    start_time: '2026-11-20T09:00:00+08:00',
    end_time: '2026-11-20T17:00:00+08:00',
    status: 'cancelled',
  },
]

/** Boardroom Five is blocked on 22 November, 09:00 to 18:00. A block is not padded. */
export const MOCK_VENUE_BLOCKS: readonly MockVenuePeriod[] = [
  {
    venue_id: MOCK_SEARCH_VENUES.boardroomFive.id,
    start_time: '2026-11-22T09:00:00+08:00',
    end_time: '2026-11-22T18:00:00+08:00',
  },
]
