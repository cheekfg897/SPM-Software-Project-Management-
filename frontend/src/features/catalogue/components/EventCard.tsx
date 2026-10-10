import type { CatalogueEvent } from '../api'
import { formatTimeRange } from '@/lib/formatDate'

import { RegisterAction } from './RegisterAction'

/** Decorative artwork, one of these picked by the event's id so a card always looks the same. */
const ART_GRADIENTS = [
  'from-corona via-flare to-ember',
  'from-flare via-ember to-nebula',
  'from-nebula via-ember to-flare',
  'from-corona via-nebula to-void',
] as const

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

/** A small black hole: a glowing ring around a dark core. */
function EventArt({ eventId }: { eventId: number }) {
  const gradient = ART_GRADIENTS[eventId % ART_GRADIENTS.length]
  return (
    <div
      aria-hidden="true"
      className={`relative hidden size-24 shrink-0 overflow-hidden rounded-xl bg-gradient-to-br sm:block ${gradient}`}
    >
      <div className="bg-void absolute inset-[22%] rounded-full shadow-[0_0_18px_6px_rgb(6_5_11/0.6)]" />
    </div>
  )
}

/** The event's places as the backend reports them. */
function PlacesStatus({ event }: { event: CatalogueEvent }) {
  if (event.is_registered) {
    return <p className="text-success text-sm font-medium">You&apos;re registered</p>
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
      <EventArt eventId={event.id} />
    </article>
  )
}
