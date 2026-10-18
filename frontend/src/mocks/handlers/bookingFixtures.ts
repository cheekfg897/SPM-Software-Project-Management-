import type { BookingRequest } from '@/features/booking/api'

import { MOCK_ACCOUNTS } from '../fixtures/accounts'

/** An event as the booking mock knows it: only what a booking request carries from the event. */
export interface MockBookingEvent {
  id: number
  reference: string
  coordinator_id: number
  status: 'approved' | 'confirmed'
  expected_attendance: number
  proposed_date: string
  end_date: string | null
  start_time: string
  end_time: string
  accessibility_needs: string | null
}

export interface MockBookingVenue {
  id: number
  capacity: number
}

const APPROVED_EVENT: MockBookingEvent = {
  id: 101,
  reference: 'EVR-BOOK0101',
  coordinator_id: MOCK_ACCOUNTS.coordinator.id,
  status: 'approved',
  expected_attendance: 80,
  proposed_date: '2026-11-10',
  end_date: null,
  start_time: '09:00:00',
  end_time: '17:00:00',
  accessibility_needs: 'Step-free access',
}

/**
 * Five events: one the coordinator can book for, one already confirmed, one assigned
 * elsewhere, and two whose requests are waiting for Venue Staff (SCRUM-43). The waiting
 * two run on different dates, so the queue's order is visible.
 */
export const MOCK_BOOKING_EVENTS = {
  approved: APPROVED_EVENT,
  confirmed: { ...APPROVED_EVENT, id: 102, reference: 'EVR-BOOK0102', status: 'confirmed' },
  someoneElses: { ...APPROVED_EVENT, id: 103, reference: 'EVR-BOOK0103', coordinator_id: 999 },
  laterShowcase: {
    ...APPROVED_EVENT,
    id: 104,
    reference: 'EVR-BOOK0104',
    proposed_date: '2026-12-01',
    start_time: '10:00:00',
  },
  earlierWorkshop: {
    ...APPROVED_EVENT,
    id: 105,
    reference: 'EVR-BOOK0105',
    proposed_date: '2026-11-20',
  },
} as const satisfies Record<string, MockBookingEvent>

/** One venue that fits the approved event's 80 guests and one that does not. */
export const MOCK_BOOKING_VENUES = {
  roomy: { id: 1, capacity: 200 },
  tiny: { id: 2, capacity: 20 },
} as const satisfies Record<string, MockBookingVenue>

/**
 * The requests waiting for a decision when a test starts, raised in the opposite order
 * to the one the queue shows them in: the backend orders by the event's date, not by id.
 */
export const MOCK_PENDING_DECISIONS = [
  {
    id: 9002,
    event_id: MOCK_BOOKING_EVENTS.laterShowcase.id,
    venue_id: 2,
    starts_at: '2026-12-01T10:00:00+08:00',
    ends_at: '2026-12-01T16:00:00+08:00',
    purpose: 'Main hall',
    expected_occupancy: 150,
    required_layout: 'theatre',
    justification: null,
    status: 'pending',
    decision_reason: null,
    preparation_status: 'not_started',
    preparation_notes: null,
    hold_expires_at: null,
    needs_alternative_venue: false,
    unavailability: [],
    replaces_request_id: null,
    event_proposed_date: MOCK_BOOKING_EVENTS.laterShowcase.proposed_date,
    event_end_date: MOCK_BOOKING_EVENTS.laterShowcase.end_date,
    event_start_time: MOCK_BOOKING_EVENTS.laterShowcase.start_time,
    event_end_time: MOCK_BOOKING_EVENTS.laterShowcase.end_time,
    accessibility_needs: MOCK_BOOKING_EVENTS.laterShowcase.accessibility_needs,
  },
  {
    id: 9001,
    event_id: MOCK_BOOKING_EVENTS.earlierWorkshop.id,
    venue_id: 1,
    starts_at: '2026-11-20T09:00:00+08:00',
    ends_at: '2026-11-20T12:00:00+08:00',
    purpose: 'Breakout room',
    expected_occupancy: 40,
    required_layout: 'classroom',
    justification: null,
    status: 'pending',
    decision_reason: null,
    preparation_status: 'not_started',
    preparation_notes: null,
    hold_expires_at: null,
    needs_alternative_venue: false,
    unavailability: [],
    replaces_request_id: null,
    event_proposed_date: MOCK_BOOKING_EVENTS.earlierWorkshop.proposed_date,
    event_end_date: MOCK_BOOKING_EVENTS.earlierWorkshop.end_date,
    event_start_time: MOCK_BOOKING_EVENTS.earlierWorkshop.start_time,
    event_end_time: MOCK_BOOKING_EVENTS.earlierWorkshop.end_time,
    accessibility_needs: MOCK_BOOKING_EVENTS.earlierWorkshop.accessibility_needs,
  },
] as const satisfies readonly BookingRequest[]
