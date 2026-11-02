import { PreparationSummary } from '@/components/preparation/PreparationSummary'
import { EmptyState } from '@/components/ui'
import { LAYOUT_OPTIONS } from '@/config/roomLayouts'
import { unavailabilityText } from '@/config/unavailabilityCategories'
import { REASSESSMENT_KIND_LABELS, STATUS_LABELS } from '@/features/booking/constants'
import { suggestionText } from '@/features/booking/suggestion'
import { formatDateTime, formatShortDate, formatTimeRange } from '@/lib/formatDate'

import type { RecordVenueArrangement } from '../api'

const NONE_ARRANGED = 'No venue is arranged for this event yet.'
const NONE_LISTED = 'none listed'

/** The layout in words, or that none was asked for, as a booking request's details say it. */
function layoutLabel(layout: string | null): string {
  const option = LAYOUT_OPTIONS.find((candidate) => candidate.value === layout)
  return option?.label ?? 'No layout set'
}

/** A venue's facilities or features as one line, or that it lists none. */
function listed(values: string[]): string {
  return values.length === 0 ? NONE_LISTED : values.join(', ')
}

/** When an On Hold arrangement's hold expires, or an Expired one's did (SCRUM-93 AC5). */
function holdText(arrangement: RecordVenueArrangement): string | null {
  if (arrangement.hold_expires_at === null) {
    return null
  }
  const when = formatDateTime(arrangement.hold_expires_at)
  if (arrangement.status === 'expired') {
    return `Hold expired ${when}`
  }
  return `Hold expires ${when}`
}

/** One flag on an arrangement and each reason for it (SCRUM-92 AC1, SCRUM-33 AC6). */
function ArrangementFlag({ heading, reasons }: { heading: string; reasons: string[] }) {
  return (
    <div className="border-danger/40 bg-danger/10 mt-3 rounded-xl border p-3">
      <p className="text-danger font-medium">{heading}</p>
      <ul aria-label={heading} className="text-ink mt-1 space-y-1">
        {/* By place: two flags may give the same reason. */}
        {reasons.map((reason, index) => (
          <li key={index}>{reason}</li>
        ))}
      </ul>
    </div>
  )
}

/**
 * What the venue offers (as the Safety Officer reviews it, SCRUM-97), what the coordinator asked
 * for, Venue Staff's reason and any alternative they suggested (SCRUM-70 AC3), any hold's expiry
 * and each flag with its reason (SCRUM-24 AC9, AC10, SCRUM-93 AC5).
 */
function ArrangementDetails({ arrangement }: { arrangement: RecordVenueArrangement }) {
  const hold = holdText(arrangement)
  const reassessments = arrangement.reassessment_flags.map(
    (flag) => `${REASSESSMENT_KIND_LABELS[flag.kind]}: ${flag.reason}`,
  )
  const suggestion = suggestionText(
    arrangement.suggested_venue_name,
    arrangement.suggested_starts_at,
    arrangement.suggested_ends_at,
  )
  return (
    <>
      <p className="text-ink-muted text-sm">
        Holds {arrangement.venue_capacity} · Facilities: {listed(arrangement.venue_facilities)} ·
        Accessibility: {listed(arrangement.venue_accessibility_features)}
      </p>
      <p className="text-ink-muted text-sm">
        {arrangement.purpose} · {arrangement.expected_occupancy} guests ·{' '}
        {layoutLabel(arrangement.required_layout)}
      </p>
      {arrangement.justification !== null && (
        <p className="text-ink-muted text-sm">Why this venue: {arrangement.justification}</p>
      )}
      {arrangement.decision_reason !== null && (
        <p className="text-ink-muted text-sm">Venue Staff: {arrangement.decision_reason}</p>
      )}
      {suggestion !== null && (
        <p className="text-ink-muted text-sm">Suggested instead: {suggestion}</p>
      )}
      {hold !== null && <p className="text-flare text-sm font-medium">{hold}</p>}
      {arrangement.needs_alternative_venue && (
        <ArrangementFlag
          heading="Needs an alternative venue"
          reasons={arrangement.unavailability.map(unavailabilityText)}
        />
      )}
      {arrangement.flagged_after_change && (
        <ArrangementFlag heading="Flagged for re-review" reasons={reassessments} />
      )}
    </>
  )
}

/**
 * Every one of the event's venue arrangements, earliest first as the backend sends them: each
 * venue and where it is, when, where its request stands, everything else on it, and Venue Staff's
 * preparation (SCRUM-24 AC9, AC10, SCRUM-84 AC2, ADR-0104, ADR-0105).
 */
export function VenueArrangementList({ arrangements }: { arrangements: RecordVenueArrangement[] }) {
  if (arrangements.length === 0) {
    return <EmptyState message={NONE_ARRANGED} />
  }
  return (
    <ul className="space-y-3">
      {arrangements.map((arrangement) => (
        <li
          key={`${arrangement.venue_name}-${arrangement.starts_at}`}
          className="border-line/60 bg-surface/50 rounded-2xl border p-5"
        >
          <p className="text-ink font-medium">{arrangement.venue_name}</p>
          <p className="text-ink-muted text-sm">{arrangement.venue_location}</p>
          <p className="text-ink-muted text-sm">
            {formatShortDate(arrangement.starts_at)},{' '}
            {formatTimeRange(arrangement.starts_at, arrangement.ends_at)} ·{' '}
            {STATUS_LABELS[arrangement.status]}
          </p>
          <ArrangementDetails arrangement={arrangement} />
          <PreparationSummary preparation={arrangement} />
        </li>
      ))}
    </ul>
  )
}
