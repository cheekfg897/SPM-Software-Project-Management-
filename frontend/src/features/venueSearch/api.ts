import { apiRequest } from '@/lib/api'

/** The venue module's search endpoint (backend/app/modules/venue/routes.py, SCRUM-35). */
const VENUE_SEARCH_PATHS = {
  SEARCH: '/api/venues/search',
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

export const venueSearchKeys = {
  all: ['venueSearch'] as const,
  results: (search: VenueSearchRequest) => [...venueSearchKeys.all, 'results', search] as const,
}

/** Venues that meet the event's needs and are free for its period, ordered by the backend. */
export function searchVenues(search: VenueSearchRequest): Promise<VenueSearchResult> {
  return apiRequest<VenueSearchResult>(VENUE_SEARCH_PATHS.SEARCH, { method: 'POST', body: search })
}
