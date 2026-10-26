import { PreparationSummary } from '@/components/preparation/PreparationSummary'
import { EmptyState } from '@/components/ui'
import { LAYOUT_OPTIONS } from '@/config/roomLayouts'
import { unavailabilityText } from '@/config/unavailabilityCategories'
import { REASSESSMENT_KIND_LABELS, STATUS_LABELS } from '@/features/booking/constants'
import { formatDateTime, formatShortDate, formatTimeRange } from '@/lib/formatDate'

import type { RecordVenueArrangement, StaffVenueArrangement } from '../api'

const NONE_ARRANGED = 'No venue is arranged for this event yet.'

/** Whether the backend sent the arrangement in full, as the organiser's record does (ADR-0104). */
function isInFull(arrangement: StaffVenueArrangement): arrangement is RecordVenueArrangement {
  return 'venue_location' in arrangement
}

/** The layout in words, or that none was asked for, as a booking request's details say it. */
function layoutLabel(layout: string | null): string {
  const option = LAYOUT_OPTIONS.find((candidate) => candidate.value === layout)
  return option?.label ?? 'No layout set'
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
 * What the coordinator asked for, Venue Staff's reason, any hold's expiry and each flag with its
 * reason: the rest of an arrangement sent in full (SCRUM-24 AC10, SCRUM-93 AC5).
 */
function ArrangementDetails({ arrangement }: { arrangement: RecordVenueArrangement }) {
  const hold = holdText(arrangement)
  const reassessments = arrangement.reassessment_flags.map(
    (flag) => `${REASSESSMENT_KIND_LABELS[flag.kind]}: ${flag.reason}`,
  )
  return (
    <>
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
      {hold !== null && <p className="text-flare text-sm font-medium">{hold}</p>}
      {arrangement.needs_alternative_venue && (
        <ArrangementFlag
          heading="Needs an alternative venue"
          reasons={arrangement.unavailability.map(unavailabilityText)}
        />
      )}
      {arrangement.flagged_after_change && (
        <ArrangementFlag heading="Flagged after a change to the event" reasons={reassessments} />
      )}
    </>
  )
}

/**
 * The event's venue arrangements, earliest first as the backend sends them: each venue, when,
 * where its request stands, and Venue Staff's preparation (SCRUM-84 AC2, ADR-0095). An
 * arrangement sent in full also says where the venue is and everything else on it (ADR-0104).
 */
export function VenueArrangementList({ arrangements }: { arrangements: StaffVenueArrangement[] }) {
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
          {isInFull(arrangement) && (
            <p className="text-ink-muted text-sm">{arrangement.venue_location}</p>
          )}
          <p className="text-ink-muted text-sm">
            {formatShortDate(arrangement.starts_at)},{' '}
            {formatTimeRange(arrangement.starts_at, arrangement.ends_at)} ·{' '}
            {STATUS_LABELS[arrangement.status]}
          </p>
          {isInFull(arrangement) && <ArrangementDetails arrangement={arrangement} />}
          <PreparationSummary preparation={arrangement} />
        </li>
      ))}
    </ul>
  )
}
