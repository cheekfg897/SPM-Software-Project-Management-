import { useId } from 'react'
import type { ReactNode } from 'react'

import { StatusChip } from '@/components/ui'
import { LAYOUT_OPTIONS } from '@/features/booking/constants'
import { formatSchedule } from '@/features/eventRequests/formatSchedule'
import { formatShortDate, formatTimeRange } from '@/lib/formatDate'

import type {
  AwaitingSafetyReview,
  EquipmentStatus,
  SafetyReviewEquipment,
  SafetyReviewVenue,
} from '../api'

/** Technical Support's outcome in words, as the backend names it (EquipmentLineStatus). */
const EQUIPMENT_STATUS_LABELS: Record<EquipmentStatus, string> = {
  requested: 'Requested',
  fulfilled: 'Fulfilled',
  partially_fulfilled: 'Partially fulfilled',
  unavailable: 'Unavailable',
}
const NOTHING_LISTED = 'None listed'

function Detail({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-ink-faint text-xs tracking-wide uppercase">{term}</dt>
      <dd className="text-ink mt-0.5">{children}</dd>
    </div>
  )
}

function SectionHeading({ children }: { children: string }) {
  return (
    <h3 className="text-ink-faint text-xs font-semibold tracking-wide uppercase">{children}</h3>
  )
}

/** A list of free-text values (facilities, features) as one line, or that there are none. */
function listed(values: string[]): string {
  return values.length === 0 ? NOTHING_LISTED : values.join(', ')
}

function layoutLabel(layout: string): string {
  const option = LAYOUT_OPTIONS.find((candidate) => candidate.value === layout)
  return option?.label ?? layout
}

function VenueItem({ venue }: { venue: SafetyReviewVenue }) {
  const nameId = useId()
  const layouts = venue.layouts.map(layoutLabel)
  return (
    <li aria-labelledby={nameId} className="border-line/70 bg-surface-raised rounded-xl border p-4">
      <p id={nameId} className="text-ink font-medium">
        {venue.name}
      </p>
      <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
        <Detail term="Booked">
          {formatShortDate(venue.starts_at)}, {formatTimeRange(venue.starts_at, venue.ends_at)}
        </Detail>
        <Detail term="Capacity">{venue.capacity}</Detail>
        <Detail term="Room layouts">{listed(layouts)}</Detail>
        <Detail term="Facilities">{listed(venue.facilities)}</Detail>
        <Detail term="Accessibility features">{listed(venue.accessibility_features)}</Detail>
      </dl>
    </li>
  )
}

/** Technical Support's answer: the outcome, with how many they will provide once they decided. */
function equipmentOutcome(equipment: SafetyReviewEquipment): string {
  const label = EQUIPMENT_STATUS_LABELS[equipment.status]
  if (equipment.provided_quantity === null) {
    return label
  }
  return `${label}, ${equipment.provided_quantity} provided`
}

function EquipmentItem({ equipment }: { equipment: SafetyReviewEquipment }) {
  const nameId = useId()
  return (
    <li
      aria-labelledby={nameId}
      className="border-line/70 bg-surface-raised rounded-xl border p-4 text-sm"
    >
      <p id={nameId} className="text-ink text-base font-medium">
        {equipment.equipment_type_name}
      </p>
      <p className="text-ink-muted mt-1">{equipment.quantity} requested</p>
      {equipment.notes !== null && (
        <p className="text-ink-muted">
          Note: <span>{equipment.notes}</span>
        </p>
      )}
      <p className="text-ink mt-2">
        Technical Support: <span>{equipmentOutcome(equipment)}</span>
      </p>
      {equipment.outcome_note !== null && (
        <p className="text-ink-faint">{equipment.outcome_note}</p>
      )}
    </li>
  )
}

/** One event awaiting the safety check: what the system holds about it (SCRUM-97 AC6). */
export function SafetyReviewCard({ awaiting }: { awaiting: AwaitingSafetyReview }) {
  const headingId = useId()
  const { event, venues, equipment } = awaiting

  return (
    <article aria-labelledby={headingId} className="border-line bg-surface rounded-2xl border p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-flare text-sm font-medium">{formatSchedule(event)}</p>
          <h2 id={headingId} className="font-display mt-1 text-xl font-semibold">
            {event.name}
          </h2>
          <p className="text-ink-faint mt-1 text-sm">{event.reference}</p>
        </div>
        <StatusChip status={event.status} />
      </div>

      <dl className="mt-5 grid gap-4 sm:grid-cols-2">
        <Detail term="Expected attendance">{event.expected_attendance}</Detail>
        <Detail term="Accessibility needs">{event.accessibility_needs ?? 'None given'}</Detail>
      </dl>

      <section className="mt-6 space-y-3">
        <SectionHeading>Venues</SectionHeading>
        {venues.length === 0 ? (
          <p className="text-ink-muted text-sm">No venue booked.</p>
        ) : (
          <ul className="grid gap-3 lg:grid-cols-2">
            {venues.map((venue) => (
              <VenueItem key={`${venue.name}-${venue.starts_at}`} venue={venue} />
            ))}
          </ul>
        )}
      </section>

      <section className="mt-6 space-y-3">
        <SectionHeading>Equipment</SectionHeading>
        {equipment.length === 0 ? (
          <p className="text-ink-muted text-sm">No equipment requested.</p>
        ) : (
          <ul className="grid gap-3 lg:grid-cols-2">
            {equipment.map((line, index) => (
              // The backend sends no ids here (ADR-0047), and the list never reorders.
              <EquipmentItem key={index} equipment={line} />
            ))}
          </ul>
        )}
      </section>
    </article>
  )
}
