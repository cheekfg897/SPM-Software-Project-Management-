import { Link } from 'react-router'

import { EventArt } from '@/components/ui'
import { ROUTES } from '@/config/routes'
import { formatTimeRange } from '@/lib/formatDate'

import type { CatalogueEvent } from '../api'

import { RegisterAction } from './RegisterAction'

function PinIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" fill="none" className="size-4 shrink-0">
      <path
        d="M10 17s5-4.6 5-8.5a5 5 0 1 0-10 0C5 12.4 10 17 10 17Z"
        stroke="currentColor"
        strokeWidth="1.5"
      />
      <circle cx="10" cy="8.5" r="1.8" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  )
}

/**
 * The event's places as the backend reports them. Once the attendee holds a place, it says so
 * and links to their own events, where it now appears (SCRUM-52 AC5).
 */
function PlacesStatus({ event }: { event: CatalogueEvent }) {
  if (event.is_registered) {
    return (
      <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-sm font-medium">
        <span className="text-success">You&apos;re registered</span>
        <Link
          to={ROUTES.MY_EVENTS}
          className="text-ink-muted hover:text-ink underline underline-offset-4 transition"
        >
          View in My events
        </Link>
      </p>
    )
  }
  if (event.is_full) {
    return <p className="text-ink-faint text-sm font-medium">Full</p>
  }
  const noun = event.places_left === 1 ? 'place' : 'places'
  return (
    <p className="text-ink-muted text-sm">
      {event.places_left} {noun} left
    </p>
  )
}

export function EventCard({ event }: { event: CatalogueEvent }) {
  return (
    <article className="border-line/70 bg-surface/70 hover:border-flare/40 hover:bg-surface-raised flex gap-5 rounded-2xl border p-5 transition">
      <div className="min-w-0 flex-1">
        <p className="text-flare text-sm font-medium">
          {formatTimeRange(event.starts_at, event.ends_at)}
        </p>
        <h3 className="font-display text-ink mt-1 text-xl font-semibold tracking-tight">
          {event.name}
        </h3>
        <p className="text-ink-muted mt-1.5 flex items-center gap-1.5 text-sm">
          <PinIcon />
          <span className="truncate">{event.venue?.name ?? 'Venue to be announced'}</span>
        </p>
        <p className="text-ink-faint mt-2 line-clamp-2 text-sm">{event.description}</p>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <PlacesStatus event={event} />
          <RegisterAction event={event} />
        </div>
      </div>
      <EventArt seed={event.id} />
    </article>
  )
}
