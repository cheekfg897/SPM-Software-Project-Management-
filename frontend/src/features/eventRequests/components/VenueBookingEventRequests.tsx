import { ROLE } from '@/config/roles'
import { staffEventPath } from '@/config/routes'
import { selectSessionUser, useAppSelector } from '@/store'

import type { EventListRow } from '../api'
import { useEventRequestsWithVenueBookings } from '../hooks'

import { RequestListSection } from './RequestListSection'

const TITLE = 'Events with venue bookings'

/** Each row opens the event's read-only record, its venue preparation included (ADR-0095). */
function pathFor(request: EventListRow): string {
  return staffEventPath(request.reference)
}

function VenueBookingList() {
  const requests = useEventRequestsWithVenueBookings()
  return <RequestListSection title={TITLE} requests={requests} pathFor={pathFor} />
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
