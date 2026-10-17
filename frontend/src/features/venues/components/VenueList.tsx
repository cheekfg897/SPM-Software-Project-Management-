import { Link } from 'react-router'

import { Button, EmptyState, ErrorAlert, EventArt, Spinner } from '@/components/ui'
import { venuePath } from '@/config/routes'

import type { Venue } from '../api'
import { useVenues } from '../hooks'

function ArrowIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" fill="none" className="size-5 shrink-0">
      <path d="M7 4l6 6-6 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
}

/** One venue as a row of the list, linking to its page. */
function VenueRow({ venue }: { venue: Venue }) {
  return (
    <Link
      to={venuePath(venue.id)}
      className="hover:bg-surface-raised flex items-center gap-5 rounded-xl p-3 transition"
    >
      <EventArt seed={venue.id} />
      <span className="min-w-0 flex-1">
        <span className="font-display text-ink block truncate text-lg font-semibold tracking-tight">
          {venue.name}
        </span>
        <span className="text-ink-muted mt-1 block truncate text-sm">{venue.location}</span>
        <span className="text-flare mt-1 block text-sm font-medium">
          Up to {venue.capacity} people
        </span>
      </span>
      <span className="text-ink-faint">
        <ArrowIcon />
      </span>
    </Link>
  )
}

/** The active venues, in the order the backend sent them (by name). */
export function VenueList() {
  const venues = useVenues()

  if (venues.isPending) {
    return (
      <p role="status" className="text-ink-muted flex items-center gap-3">
        <Spinner />
        Loading venues…
      </p>
    )
  }
  if (venues.isError) {
    return (
      <div className="space-y-4">
        <ErrorAlert error={venues.error} />
        <Button variant="secondary" onClick={() => void venues.refetch()}>
          Try again
        </Button>
      </div>
    )
  }
  if (venues.data.length === 0) {
    return <EmptyState message="No venues are listed yet." />
  }
  return (
    <ul
      aria-label="Venues"
      className="border-line/70 bg-surface/70 space-y-1 rounded-2xl border p-2"
    >
      {venues.data.map((venue) => (
        <li key={venue.id}>
          <VenueRow venue={venue} />
        </li>
      ))}
    </ul>
  )
}
