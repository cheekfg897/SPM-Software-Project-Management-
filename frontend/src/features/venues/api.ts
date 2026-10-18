import type { VenueLayout } from '@/config/venueLayouts'
import { apiRequest } from '@/lib/api'

import type { Weekday } from './constants'

/** The venue module's catalogue endpoints (SCRUM-25, SCRUM-67). */
const VENUE_PATHS = {
  VENUES: '/api/venues',
  venue: (venueId: number) => `/api/venues/${venueId}`,
  deactivate: (venueId: number) => `/api/venues/${venueId}/deactivate`,
  reactivate: (venueId: number) => `/api/venues/${venueId}/reactivate`,
} as const

/** One end of an opening period: a weekday and a 24-hour `HH:MM` time (ADR-0008). */
export interface DayTime {
  day: Weekday
  time: string
}

/** One period the venue is open. It may close the day after it opens (ADR-0008). */
export interface OpeningPeriod {
  open: DayTime
  close: DayTime
}

/** A venue as every venue route returns it. */
export interface Venue {
  id: number
  name: string
  location: string
  capacity: number
  facilities: string[]
  accessibility_features: string[]
  supported_layouts: VenueLayout[]
  /** The weekly schedule in week order; none means closed all week. */
  opening_hours: OpeningPeriod[]
  /** Minutes the venue is held before and after each event (SCRUM-67, ADR-0011). */
  setup_minutes: number
  turnaround_minutes: number
  is_active: boolean
}

/**
 * What the venue form sends. `capacity` is null when the field was left empty, so the backend
 * refuses it rather than a change keeping the old value (ADR-0067). The two times are left out
 * to take the standard time on a new venue, or to keep the venue's own on a change.
 */
export interface VenueDetails {
  name: string
  location: string
  capacity: number | null
  facilities: string[]
  accessibility_features: string[]
  supported_layouts: string[]
  opening_hours: OpeningPeriod[]
  setup_minutes?: number
  turnaround_minutes?: number
}

/** Two confirmed bookings whose periods, padded by setup and turnaround, now overlap. */
export interface OverlapWarning {
  booking_ids: number[]
  overlap_start: string
  overlap_end: string
}

/** A confirmed booking whose padded period now runs into one of the venue's blocks (ADR-0033). */
export interface BlockOverlapWarning {
  booking_id: number
  block_id: number
  overlap_start: string
  overlap_end: string
}

/** What a change returns: the venue, and what a new setup or turnaround time now overlaps. */
export interface UpdatedVenue extends Venue {
  overlap_warnings: OverlapWarning[]
  block_overlap_warnings: BlockOverlapWarning[]
}

/** Nothing about a venue depends on who reads it, so its keys don't name the viewer. */
export const venueKeys = {
  all: ['venues'] as const,
  list: () => [...venueKeys.all, 'list'] as const,
  detail: (venueId: number) => [...venueKeys.all, 'detail', venueId] as const,
}

/** The active venues, in the backend's order (by name). */
export function fetchVenues(): Promise<Venue[]> {
  return apiRequest<Venue[]>(VENUE_PATHS.VENUES)
}

/** One venue, active or not. */
export function fetchVenue(venueId: number): Promise<Venue> {
  return apiRequest<Venue>(VENUE_PATHS.venue(venueId))
}

export function createVenue(details: VenueDetails): Promise<Venue> {
  return apiRequest<Venue>(VENUE_PATHS.VENUES, { method: 'POST', body: details })
}

export function updateVenue(venueId: number, changes: VenueDetails): Promise<UpdatedVenue> {
  return apiRequest<UpdatedVenue>(VENUE_PATHS.venue(venueId), { method: 'PATCH', body: changes })
}

export function deactivateVenue(venueId: number): Promise<Venue> {
  return apiRequest<Venue>(VENUE_PATHS.deactivate(venueId), { method: 'POST' })
}

export function reactivateVenue(venueId: number): Promise<Venue> {
  return apiRequest<Venue>(VENUE_PATHS.reactivate(venueId), { method: 'POST' })
}
