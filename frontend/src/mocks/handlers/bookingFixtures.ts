import { MOCK_ACCOUNTS } from '../fixtures/accounts'

/** An event as the booking mock knows it: only what a booking request carries from the event. */
export interface MockBookingEvent {
  id: number
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
  coordinator_id: MOCK_ACCOUNTS.coordinator.id,
  status: 'approved',
  expected_attendance: 80,
  proposed_date: '2026-11-10',
  end_date: null,
  start_time: '09:00:00',
  end_time: '17:00:00',
  accessibility_needs: 'Step-free access',
}

/** Three events: one the coordinator can book for, one already confirmed, one assigned elsewhere. */
export const MOCK_BOOKING_EVENTS = {
  approved: APPROVED_EVENT,
  confirmed: { ...APPROVED_EVENT, id: 102, status: 'confirmed' },
  someoneElses: { ...APPROVED_EVENT, id: 103, coordinator_id: 999 },
} as const satisfies Record<string, MockBookingEvent>

/** One venue that fits the approved event's 80 guests and one that does not. */
export const MOCK_BOOKING_VENUES = {
  roomy: { id: 1, capacity: 200 },
  tiny: { id: 2, capacity: 20 },
} as const satisfies Record<string, MockBookingVenue>
