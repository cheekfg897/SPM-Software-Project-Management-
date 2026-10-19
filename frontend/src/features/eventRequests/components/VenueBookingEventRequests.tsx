import { ROLE } from '@/config/roles'
import { selectSessionUser, useAppSelector } from '@/store'

import { useEventRequestsWithVenueBookings } from '../hooks'

import { RequestListSection } from './RequestListSection'

const TITLE = 'Events with venue bookings'

/**
 * The rows open nothing: Venue Staff can't open an event's record, and have no page for one
 * event's arrangements (ADR-0090).
 */
function VenueBookingList() {
  const requests = useEventRequestsWithVenueBookings()
  return <RequestListSection title={TITLE} requests={requests} />
}

/**
 * On Staff home, every event with a venue booking request or a booking, newest first, for Venue
 * Staff (SCRUM-24 AC4, AC8, AC11; ADR-0085, ADR-0090). Other roles see none, and nothing is
 * asked for.
 */
export function VenueBookingEventRequests() {
  const viewer = useAppSelector(selectSessionUser)
  if (viewer?.role !== ROLE.VENUE_STAFF) {
    return null
  }
  return <VenueBookingList />
}
