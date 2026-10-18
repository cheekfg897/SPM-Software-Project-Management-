import { skipToken, useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router'

import { searchVenues, venueSearchKeys } from './api'
import { readFilters, toSearchRequest, withFilters } from './searchParams'
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
