import type { VenueLayout } from '@/config/venueLayouts'
import { apiRequest } from '@/lib/api'

import type { Weekday } from './constants'

/** The venue module's catalogue (SCRUM-25, SCRUM-67), block (SCRUM-34) and calendar (SCRUM-26) endpoints. */
const VENUE_PATHS = {
  VENUES: '/api/venues',
  venue: (venueId: number) => `/api/venues/${venueId}`,
  deactivate: (venueId: number) => `/api/venues/${venueId}/deactivate`,
  reactivate: (venueId: number) => `/api/venues/${venueId}/reactivate`,
  blocks: (venueId: number) => `/api/venues/${venueId}/blocks`,
  block: (venueId: number, blockId: number) => `/api/venues/${venueId}/blocks/${blockId}`,
  calendar: (venueId: number) => `/api/venues/${venueId}/calendar`,
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

/** A period a venue is blocked for maintenance or internal use (SCRUM-34), in business time. */
export interface VenueBlock {
  id: number
  venue_id: number
  start_time: string
  end_time: string
  reason: string
}

/**
 * What the block form sends. The times are as a date-time input holds them, with no offset,
 * which the backend reads as business time (ADR-0009, ADR-0068).
 */
export interface NewBlock {
  start_time: string
  end_time: string
  reason: string
}

/** A confirmed booking a new block cuts into, as the period it holds the venue (ADR-0016). */
export interface ConflictingBooking {
  booking_id: number
  event_id: number | null
  start_time: string
  end_time: string
}

/** A saved block, and the confirmed bookings it cuts into (SCRUM-34 AC2). */
export interface CreatedBlock extends VenueBlock {
  conflicting_bookings: ConflictingBooking[]
}

export type CalendarEntryKind = 'confirmed_booking' | 'tentative_hold' | 'block'

/**
 * One period a venue is unavailable (SCRUM-26). A booking is shown as the period it holds the
 * venue, padded by setup and turnaround, with its event's own times beside it; a block has none.
 * How much `reason` says depends on who asks (AC3).
 */
export interface CalendarEntry {
  start_time: string
  end_time: string
  event_start: string | null
  event_end: string | null
  kind: CalendarEntryKind
  reason: string
}

/** The two instants the calendar route takes, here without an offset (business time). */
export interface CalendarRange {
  range_start: string
  range_end: string
}

/**
 * A venue's details and blocks are the same for every staff member who reads them; the
 * calendar's reasons are not (SCRUM-26 AC3), so its key names the viewer.
 */
export const venueKeys = {
  all: ['venues'] as const,
  list: () => [...venueKeys.all, 'list'] as const,
  detail: (venueId: number) => [...venueKeys.all, 'detail', venueId] as const,
  blocks: (venueId: number) => [...venueKeys.all, 'blocks', venueId] as const,
  calendar: (venueId: number, range: CalendarRange, viewerId: number | null) =>
    [...venueKeys.all, 'calendar', venueId, viewerId, range] as const,
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

/**
 * Why a venue is being deactivated (SCRUM-92 AC9, ADR-0053): one of UNAVAILABILITY_CATEGORIES
 * and a note for the coordinators told. Both go as chosen and typed; the backend checks them.
 */
export interface Deactivation {
  category: string
  reason: string
}

export function deactivateVenue(venueId: number, deactivation: Deactivation): Promise<Venue> {
  return apiRequest<Venue>(VENUE_PATHS.deactivate(venueId), {
    method: 'POST',
    body: deactivation,
  })
}

export function reactivateVenue(venueId: number): Promise<Venue> {
  return apiRequest<Venue>(VENUE_PATHS.reactivate(venueId), { method: 'POST' })
}

/** The venue's blocks with their ids and reasons, in start order (Venue Staff only). */
export function fetchVenueBlocks(venueId: number): Promise<VenueBlock[]> {
  return apiRequest<VenueBlock[]>(VENUE_PATHS.blocks(venueId))
}

export function blockVenue(venueId: number, block: NewBlock): Promise<CreatedBlock> {
  return apiRequest<CreatedBlock>(VENUE_PATHS.blocks(venueId), { method: 'POST', body: block })
}

/** Remove a block; the backend answers 204 with no body. */
export function removeVenueBlock(venueId: number, blockId: number): Promise<void> {
  return apiRequest<undefined>(VENUE_PATHS.block(venueId, blockId), { method: 'DELETE' })
}

/** The venue's unavailable periods that touch the range, in time order (SCRUM-26). */
export function fetchVenueCalendar(
  venueId: number,
  range: CalendarRange,
): Promise<CalendarEntry[]> {
  return apiRequest<CalendarEntry[]>(VENUE_PATHS.calendar(venueId), { query: { ...range } })
}
