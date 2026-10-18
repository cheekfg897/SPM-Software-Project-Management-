import { EmptyState, ErrorAlert, Spinner } from '@/components/ui'

import { useVenueSearch, useVenueSearchFilters } from '../hooks'

import { VenueMatchCard } from './VenueMatchCard'

const HEADING_ID = 'venue-results-heading'

/** The backend's answer to the search in the URL, in its order, or its message for none. */
export function VenueSearchResults() {
  const { filters } = useVenueSearchFilters()
  const { data, error, isPending } = useVenueSearch(filters)

  if (filters === null) {
    return null
  }
  return (
    <section className="space-y-4" aria-labelledby={HEADING_ID}>
      <h2 id={HEADING_ID} className="text-xl font-semibold">
        Venues that match
      </h2>
      <ErrorAlert error={error} />
      {isPending && error === null && (
        <p className="text-ink-muted flex items-center gap-2">
          <Spinner />
          Searching venues
        </p>
      )}
      {data?.message !== undefined && <EmptyState message={data.message} />}
      {data !== undefined && data.results.length > 0 && (
        <ul aria-labelledby={HEADING_ID} className="space-y-4">
          {data.results.map((venue) => (
            <li key={venue.id}>
              <VenueMatchCard venue={venue} />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
