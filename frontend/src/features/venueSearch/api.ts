import { apiRequest } from '@/lib/api'

/** The venue module's endpoints this page calls (backend/app/modules/venue/routes.py). */
const VENUE_SEARCH_PATHS = {
  SEARCH: '/api/venues/search',
  VENUES: '/api/venues',
  suitabilityOf: (venueId: number) => `/api/venues/${venueId}/suitability`,
} as const

/** What an event asks of a venue, as search takes it. Lists may be empty; `null` is any layout. */
export interface VenueRequirements {
  required_layout: string | null
  required_facilities: string[]
  required_accessibility: string[]
}

/** The search's body: the event's period in business time, its size and its requirements. */
export interface VenueSearchRequest extends VenueRequirements {
  /** ISO date-time with an offset, in business time. */
  start_time: string
  end_time: string
  min_capacity: number
  /** Matches any venue whose location contains it; `null` is anywhere. */
  location: string | null
}

/** Which of the requested requirements a venue meets, as the backend stored them (lower case). */
export interface MatchedRequirements {
  facilities: string[]
  accessibility_features: string[]
  layout: string | null
}

/** One venue that meets the search and is free for its period. */
export interface VenueMatch {
  id: number
  name: string
  capacity: number
  location: string
  matched_requirements: MatchedRequirements
}

/** The search's answer. `message` is there only when nothing matched. */
export interface VenueSearchResult {
  results: VenueMatch[]
  message?: string
}

/** An active venue as the venue list returns it; this page reads only these fields. */
export interface VenueSummary {
  id: number
  name: string
  location: string
  capacity: number
}

/** The suitability check's body: the event's expected attendance and its requirements. */
export interface SuitabilityRequest extends VenueRequirements {
  expected_attendance: number
}

/** One requirement the venue fails, with the backend's sentence saying why. */
export interface UnmetRequirement {
  requirement: 'capacity' | 'facilities' | 'accessibility' | 'layout'
  message: string
}

/** Whether the venue can host the event; `reasons` lists every requirement it fails. */
export interface SuitabilityResult {
  suitable: boolean
  reasons: UnmetRequirement[]
}

export const venueSearchKeys = {
  all: ['venueSearch'] as const,
  results: (search: VenueSearchRequest | null) =>
    [...venueSearchKeys.all, 'results', search] as const,
  venues: () => [...venueSearchKeys.all, 'venues'] as const,
  suitability: (venueId: number, check: SuitabilityRequest) =>
    [...venueSearchKeys.all, 'suitability', venueId, check] as const,
}

/** Venues that meet the event's needs and are free for its period, ordered by the backend. */
export function searchVenues(search: VenueSearchRequest): Promise<VenueSearchResult> {
  return apiRequest<VenueSearchResult>(VENUE_SEARCH_PATHS.SEARCH, { method: 'POST', body: search })
}

/** Every active venue, ordered by name by the backend. */
export function fetchVenues(): Promise<VenueSummary[]> {
  return apiRequest<VenueSummary[]>(VENUE_SEARCH_PATHS.VENUES)
}

/** Whether one venue meets the event's needs, and each one it fails (SCRUM-36). */
export function checkSuitability(
  venueId: number,
  check: SuitabilityRequest,
): Promise<SuitabilityResult> {
  return apiRequest<SuitabilityResult>(VENUE_SEARCH_PATHS.suitabilityOf(venueId), {
    method: 'POST',
    body: check,
  })
}
