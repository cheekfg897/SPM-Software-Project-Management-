import type { ReactNode } from 'react'

import type { Venue } from '../api'
import { formatMinutes, formatPeriodHours, layoutLabel, weekdayLabel } from '../formatVenue'

import { VenueSection } from './VenueSection'

/** A term and its value, side by side from small screens up. */
const ROW_CLASSES =
  'border-line/60 grid gap-1 border-b py-3 last:border-b-0 sm:grid-cols-[12rem_minmax(0,1fr)]'

function Detail({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className={ROW_CLASSES}>
      <dt className="text-ink-muted text-sm">{term}</dt>
      <dd className="text-ink">{children}</dd>
    </div>
  )
}

/** The items as the backend sent them, or a word that there are none. */
function itemsOrNone(items: string[]): string {
  return items.length === 0 ? 'None listed' : items.join(', ')
}

const DETAILS_CLASSES = 'border-line/70 bg-surface/70 rounded-2xl border px-5 py-2'

/** Everything the backend holds about a venue, in sections (SCRUM-25 AC1, SCRUM-67). */
export function VenueProfile({ venue }: { venue: Venue }) {
  return (
    <>
      {!venue.is_active && (
        <p className="border-line text-ink-muted mt-8 rounded-xl border border-dashed px-4 py-3 text-sm">
          This venue is deactivated. It isn&apos;t listed or offered in venue search, and bookings
          already made for it keep it.
        </p>
      )}

      <VenueSection title="Details">
        <dl className={DETAILS_CLASSES}>
          <Detail term="Capacity">Up to {venue.capacity} people</Detail>
          <Detail term="Layouts">{itemsOrNone(venue.supported_layouts.map(layoutLabel))}</Detail>
          <Detail term="Facilities">{itemsOrNone(venue.facilities)}</Detail>
          <Detail term="Accessibility">{itemsOrNone(venue.accessibility_features)}</Detail>
        </dl>
      </VenueSection>

      <VenueSection
        title="Setup and turnaround"
        description="How long each booking holds the venue before its event starts and after it ends."
      >
        <dl className={DETAILS_CLASSES}>
          <Detail term="Setup">{formatMinutes(venue.setup_minutes)}</Detail>
          <Detail term="Turnaround">{formatMinutes(venue.turnaround_minutes)}</Detail>
        </dl>
      </VenueSection>

      <VenueSection title="Opening hours">
        {venue.opening_hours.length === 0 ? (
          <p className="text-ink-muted">Closed all week</p>
        ) : (
          <ul className={DETAILS_CLASSES}>
            {venue.opening_hours.map((period) => (
              <li key={`${period.open.day}-${period.open.time}`} className={ROW_CLASSES}>
                <span className="text-ink-muted text-sm">{weekdayLabel(period.open.day)}</span>
                <span className="text-ink">{formatPeriodHours(period)}</span>
              </li>
            ))}
          </ul>
        )}
      </VenueSection>
    </>
  )
}
