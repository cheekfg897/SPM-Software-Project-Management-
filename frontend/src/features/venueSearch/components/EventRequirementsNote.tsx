import { Link } from 'react-router'

import { coordinatorEventPath } from '@/config/routes'
import type { EventRequest } from '@/features/eventRequests/api'

const HEADING_ID = 'event-requirements-heading'

/** One of the event's written requirements, or that it recorded none. */
function WrittenRequirement({ label, text }: { label: string; text: string | null }) {
  return (
    <div className="grid gap-1 sm:grid-cols-3 sm:gap-4">
      <dt className="text-ink-muted">{label}</dt>
      <dd className="text-ink whitespace-pre-line sm:col-span-2">{text ?? 'None recorded'}</dd>
    </div>
  )
}

/**
 * What the event the search was opened from asked of its venue, in its own words, shown beside
 * the filters its details could not fill (SCRUM-90 AC3, ADR-0124). It says those filters are
 * the coordinator's to set, so a search filled in only partly is never taken for a complete one.
 */
export function EventRequirementsNote({ event }: { event: EventRequest }) {
  return (
    <section
      aria-labelledby={HEADING_ID}
      className="border-line bg-surface-raised space-y-3 rounded-xl border p-4 text-sm"
    >
      <h2 id={HEADING_ID} className="text-ink font-semibold">
        What {event.name} asked for
      </h2>
      <p className="text-ink">
        The date, times and minimum capacity are filled in from event {event.reference}. Room
        layout, facilities and accessibility are not filled in from the event, because it records
        them as free text: set them yourself from what it asked for.
      </p>
      <dl className="space-y-2">
        <WrittenRequirement label="Venue requirements" text={event.venue_requirements} />
        <WrittenRequirement label="Accessibility needs" text={event.accessibility_needs} />
      </dl>
      <Link to={coordinatorEventPath(event.reference)} className="text-flare underline">
        Back to the event
      </Link>
    </section>
  )
}
