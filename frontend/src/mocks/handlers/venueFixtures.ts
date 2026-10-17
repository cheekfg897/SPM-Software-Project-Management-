import type { OpeningPeriod, Venue } from '@/features/venues/api'
import type { Weekday } from '@/features/venues/constants'

import { MOCK_BOOKING_EVENTS, MOCK_BOOKING_VENUES } from './bookingFixtures'

/** A booking as the venue mock holds it: the event's own period, in business time. */
export interface MockVenueBooking {
  id: number
  venue_id: number
  event_id: number | null
  status: 'tentative' | 'confirmed' | 'cancelled'
  start_time: string
  end_time: string
}

/** A period a venue is blocked for maintenance or internal use (SCRUM-34). */
export interface MockVenueBlock {
  id: number
  venue_id: number
  start_time: string
  end_time: string
  reason: string
}

function period(openDay: Weekday, openTime: string, closeDay: Weekday, closeTime: string) {
  return {
    open: { day: openDay, time: openTime },
    close: { day: closeDay, time: closeTime },
  } satisfies OpeningPeriod
}

const WEEKDAY_HOURS: OpeningPeriod[] = [
  period('monday', '08:00', 'monday', '22:00'),
  period('tuesday', '08:00', 'tuesday', '22:00'),
  period('wednesday', '08:00', 'wednesday', '22:00'),
  period('thursday', '08:00', 'thursday', '22:00'),
  period('friday', '08:00', 'friday', '22:00'),
]

/**
 * The venues every mock run starts with, saved out of name order, since the backend lists them
 * by name. Marina Hall and Boardroom Two are the booking mock's venues 1 and 2, with the same
 * capacities. Annexe Studio is deactivated: it would come first by name if the list leaked it.
 */
export const MOCK_VENUES = {
  marinaHall: {
    id: MOCK_BOOKING_VENUES.roomy.id,
    name: 'Marina Hall',
    location: 'Level 1, Marina Wing',
    capacity: MOCK_BOOKING_VENUES.roomy.capacity,
    facilities: ['projector', 'stage'],
    accessibility_features: ['step-free access', 'hearing loop'],
    supported_layouts: ['theatre', 'banquet'],
    opening_hours: [...WEEKDAY_HOURS, period('saturday', '18:00', 'sunday', '02:00')],
    setup_minutes: 30,
    turnaround_minutes: 30,
    is_active: true,
  },
  gardenPavilion: {
    id: 27,
    name: 'Garden Pavilion',
    location: 'East Lawn',
    capacity: 120,
    facilities: ['sound system'],
    accessibility_features: [],
    supported_layouts: ['banquet', 'exhibition'],
    opening_hours: WEEKDAY_HOURS,
    setup_minutes: 45,
    turnaround_minutes: 15,
    is_active: true,
  },
  boardroomTwo: {
    id: MOCK_BOOKING_VENUES.tiny.id,
    name: 'Boardroom Two',
    location: 'Level 3, Tower Block',
    capacity: MOCK_BOOKING_VENUES.tiny.capacity,
    facilities: ['video conferencing'],
    accessibility_features: ['lift access'],
    supported_layouts: ['boardroom'],
    opening_hours: WEEKDAY_HOURS,
    setup_minutes: 10,
    turnaround_minutes: 10,
    is_active: true,
  },
  annexeStudio: {
    id: 38,
    name: 'Annexe Studio',
    location: 'Old Wing',
    capacity: 35,
    facilities: [],
    accessibility_features: [],
    supported_layouts: ['classroom', 'other'],
    opening_hours: [],
    setup_minutes: 30,
    turnaround_minutes: 30,
    is_active: false,
  },
} satisfies Record<string, Venue>

/**
 * Marina Hall's two confirmed bookings on 10 Nov hold it 08:30 to 12:30 and 12:30 to 17:30 with
 * its 30 minutes either side, so they only touch, and the second only touches the block that
 * starts at 17:30. Any longer turnaround makes both overlap. The afternoon booking has the lower
 * id, so a report in id order rather than start order would show. Boardroom Two's bookings already
 * overlap each other, so a report that leaked another venue's bookings would show them. The
 * tentative and cancelled bookings are never part of an overlap report.
 */
export const MOCK_VENUE_BOOKINGS: readonly MockVenueBooking[] = [
  {
    id: 511,
    venue_id: MOCK_VENUES.marinaHall.id,
    event_id: MOCK_BOOKING_EVENTS.earlierWorkshop.id,
    status: 'confirmed',
    start_time: '2026-11-10T13:00:00+08:00',
    end_time: '2026-11-10T17:00:00+08:00',
  },
  {
    id: 512,
    venue_id: MOCK_VENUES.marinaHall.id,
    event_id: MOCK_BOOKING_EVENTS.approved.id,
    status: 'confirmed',
    start_time: '2026-11-10T09:00:00+08:00',
    end_time: '2026-11-10T12:00:00+08:00',
  },
  {
    id: 503,
    venue_id: MOCK_VENUES.marinaHall.id,
    event_id: MOCK_BOOKING_EVENTS.laterShowcase.id,
    status: 'tentative',
    start_time: '2026-11-10T12:00:00+08:00',
    end_time: '2026-11-10T13:00:00+08:00',
  },
  {
    id: 504,
    venue_id: MOCK_VENUES.marinaHall.id,
    event_id: null,
    status: 'cancelled',
    start_time: '2026-11-10T12:15:00+08:00',
    end_time: '2026-11-10T13:15:00+08:00',
  },
  {
    id: 505,
    venue_id: MOCK_VENUES.boardroomTwo.id,
    event_id: null,
    status: 'confirmed',
    start_time: '2026-11-10T09:00:00+08:00',
    end_time: '2026-11-10T12:00:00+08:00',
  },
  {
    id: 506,
    venue_id: MOCK_VENUES.boardroomTwo.id,
    event_id: MOCK_BOOKING_EVENTS.confirmed.id,
    status: 'confirmed',
    start_time: '2026-11-10T11:00:00+08:00',
    end_time: '2026-11-10T14:00:00+08:00',
  },
]

/** One block on each of the first two venues, both starting where a booking's turnaround ends. */
export const MOCK_VENUE_BLOCKS: readonly MockVenueBlock[] = [
  {
    id: 71,
    venue_id: MOCK_VENUES.marinaHall.id,
    start_time: '2026-11-10T17:30:00+08:00',
    end_time: '2026-11-10T20:00:00+08:00',
    reason: 'Stage lighting repair',
  },
  {
    id: 72,
    venue_id: MOCK_VENUES.boardroomTwo.id,
    start_time: '2026-11-10T14:10:00+08:00',
    end_time: '2026-11-10T16:00:00+08:00',
    reason: 'Carpet cleaning',
  },
]
