import type { ReactNode } from 'react'
import { Link } from 'react-router'

import { EventArt, StatusChip } from '@/components/ui'
import { myEventPath } from '@/config/routes'
import { formatTimeRange } from '@/lib/formatDate'

import type { MyEvent } from '../api'
import { REGISTRATION_STATUS_LABELS } from '../constants'

interface MyEventCardProps {
  event: MyEvent
  /** What the Attendee can do about this registration, if anything, such as withdrawing. */
  children?: ReactNode
}

/**
 * One of the Attendee's events: when, what, the event's own status, so a cancelled event says
 * so (SCRUM-24 AC8), and the registration's own status (SCRUM-53 AC1). Its artwork matches the
 * event's card in the catalogue, and its name opens the event's own page (SCRUM-24 AC11).
 */
export function MyEventCard({ event, children }: MyEventCardProps) {
  return (
    <article className="border-line/70 bg-surface/70 flex gap-5 rounded-2xl border p-5">
      <div className="min-w-0 flex-1">
        <p className="text-flare text-sm font-medium">
          {formatTimeRange(event.starts_at, event.ends_at)}
        </p>
        <h3 className="font-display text-ink mt-1 text-xl font-semibold tracking-tight">
          <Link to={myEventPath(event.reference)} className="hover:text-flare">
            {event.name}
          </Link>
        </h3>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <StatusChip status={event.event_status} />
          <span className="text-ink-muted text-sm">{REGISTRATION_STATUS_LABELS[event.status]}</span>
        </div>
        {children}
      </div>
      <EventArt seed={event.event_id} />
    </article>
  )
}
