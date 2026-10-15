import { EventArt, StatusChip } from '@/components/ui'
import { formatTimeRange } from '@/lib/formatDate'

import type { MyEvent } from '../api'

/**
 * One of the Attendee's events: when, what, and the event's own status, so a cancelled event
 * says so (SCRUM-24 AC8). Its artwork matches the event's card in the catalogue.
 */
export function MyEventCard({ event }: { event: MyEvent }) {
  return (
    <article className="border-line/70 bg-surface/70 flex gap-5 rounded-2xl border p-5">
      <div className="min-w-0 flex-1">
        <p className="text-flare text-sm font-medium">
          {formatTimeRange(event.starts_at, event.ends_at)}
        </p>
        <h3 className="font-display text-ink mt-1 text-xl font-semibold tracking-tight">
          {event.name}
        </h3>
        <div className="mt-3">
          <StatusChip status={event.event_status} />
        </div>
      </div>
      <EventArt seed={event.event_id} />
    </article>
  )
}
