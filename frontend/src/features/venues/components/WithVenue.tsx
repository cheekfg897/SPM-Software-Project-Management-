import type { ReactNode } from 'react'
import { useParams } from 'react-router'

import { PageContainer } from '@/components/layout'
import { ErrorAlert, Spinner } from '@/components/ui'

import type { Venue } from '../api'
import { useVenue } from '../hooks'

/**
 * The page for the venue in the address (`:venueId`), drawn by `children` once the backend has
 * sent it. Until then, the page says it is loading, or shows why the venue can't be shown.
 */
export function WithVenue({ children }: { children: (venue: Venue) => ReactNode }) {
  // The route always supplies it; useParams just types it as possibly missing.
  const { venueId = '' } = useParams()
  const venue = useVenue(Number(venueId))

  if (venue.isPending) {
    return (
      <PageContainer title="Venue">
        <p role="status" className="text-ink-muted mt-10 flex items-center gap-3">
          <Spinner />
          Loading the venue…
        </p>
      </PageContainer>
    )
  }
  if (venue.isError) {
    return (
      <PageContainer title="Venue">
        <div className="mt-10">
          <ErrorAlert error={venue.error} />
        </div>
      </PageContainer>
    )
  }
  return children(venue.data)
}
