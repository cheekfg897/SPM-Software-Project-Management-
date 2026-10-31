import { skipToken, useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router'

import { checkSuitability, fetchVenues, searchVenues, venueSearchKeys } from './api'
import {
  readEventToSearchFor,
  readFilters,
  readReplacementSearch,
  readVenueToCheck,
  toSearchRequest,
  toSuitabilityRequest,
  withFilters,
  withVenueToCheck,
} from './searchParams'
import type { SearchFilters } from './searchParams'

/**
 * The search's filters, read from and written to the page URL. Searching adds a history entry,
 * so Back returns to the previous search.
 */
export function useVenueSearchFilters() {
  const [searchParams, setSearchParams] = useSearchParams()

  return {
    filters: readFilters(searchParams),
    applyFilters: (filters: SearchFilters) => {
      setSearchParams((current) => withFilters(current, filters))
    },
  }
}

/** The backend's answer to the filters in the URL; nothing is sent until there are some. */
export function useVenueSearch(filters: SearchFilters | null) {
  const search = filters === null ? null : toSearchRequest(filters)
  return useQuery({
    queryKey: venueSearchKeys.results(search),
    queryFn: search === null ? skipToken : () => searchVenues(search),
  })
}

/** The venue being checked, read from and written to the page URL (SCRUM-36). */
export function useVenueToCheck() {
  const [searchParams, setSearchParams] = useSearchParams()

  return {
    venueId: readVenueToCheck(searchParams),
    checkVenue: (venueId: number) => {
      setSearchParams((current) => withVenueToCheck(current, venueId))
    },
  }
}

/** Every active venue, to choose one to check. */
export function useVenues() {
  return useQuery({ queryKey: venueSearchKeys.venues(), queryFn: fetchVenues })
}

/** Whether the venue meets the needs searched for, and each one it fails. */
export function useSuitability(venueId: number, filters: SearchFilters) {
  const check = toSuitabilityRequest(filters)
  return useQuery({
    queryKey: venueSearchKeys.suitability(venueId, check),
    queryFn: () => checkSuitability(venueId, check),
  })
}

/** The flagged arrangement the search is finding a replacement for, or null (SCRUM-92). */
export function useReplacementSearch() {
  const [searchParams] = useSearchParams()
  return readReplacementSearch(searchParams)
}

/** The EVR- reference of the event the search was opened from, or null (SCRUM-90). */
export function useEventToSearchFor() {
  const [searchParams] = useSearchParams()
  return readEventToSearchFor(searchParams)
}
