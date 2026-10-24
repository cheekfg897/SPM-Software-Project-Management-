import { useId } from 'react'

import { ButtonLink } from '@/components/ui'
import { unavailabilityCategoryLabel } from '@/config/unavailabilityCategories'
import { formatDateTime } from '@/lib/formatDate'

import type { BookingRequest, Unavailability } from '../api'
import { REASSESSMENT_KIND_LABELS } from '../constants'
import { findAnotherVenuePath } from '../replacement'

/** e.g. "from 26 Nov, 8:00 am to 26 Nov, 6:00 pm"; a deactivation has no end yet. */
function periodText(cause: Unavailability): string {
  const from = `from ${formatDateTime(cause.starts_at)}`
  if (cause.ends_at === null) {
    return `${from} until the venue is reactivated`
  }
  return `${from} to ${formatDateTime(cause.ends_at)}`
}

interface AlternativeVenueNoticeProps {
  reference: string
  arrangement: BookingRequest
}

/**
 * Why a flagged arrangement needs an alternative venue, and one way to find another venue for
 * its period (SCRUM-92 AC6). For an unavailable venue, each block or deactivation the backend
 * lists, with its category, Venue Staff's note and its period in business time (AC1, AC9). For a
 * significant change, each reason it flagged the arrangement, with its kind (SCRUM-33 AC6): until
 * Venue Staff can reconfirm a booking (SCRUM-59), a replacement is how the coordinator clears it
 * (ADR-0094). The arrangement itself is shown above it as it was booked (AC4).
 */
export function AlternativeVenueNotice({ reference, arrangement }: AlternativeVenueNoticeProps) {
  const headingId = useId()
  const heading = arrangement.needs_alternative_venue
    ? 'Needs an alternative venue'
    : 'Flagged after a change to the event'

  return (
    <section
      aria-labelledby={headingId}
      className="border-danger/40 bg-danger/10 mt-3 space-y-2 rounded-xl border p-3"
    >
      <p id={headingId} className="text-danger font-medium">
        {heading}
      </p>
      {arrangement.needs_alternative_venue && (
        <ul aria-label="Why its venue is unavailable" className="text-ink space-y-1">
          {/* By place: two blocks may give the same reason for the same period. */}
          {arrangement.unavailability.map((cause, index) => (
            <li key={index}>
              {unavailabilityCategoryLabel(cause.category)}: {cause.reason}. Unavailable{' '}
              {periodText(cause)}.
            </li>
          ))}
        </ul>
      )}
      {arrangement.flagged_after_change && (
        <ul aria-label="Why a change to the event flagged it" className="text-ink space-y-1">
          {/* By place: two changes may give the same reason. */}
          {arrangement.reassessment_flags.map((flag, index) => (
            <li key={index}>
              {REASSESSMENT_KIND_LABELS[flag.kind]}: {flag.reason}
            </li>
          ))}
        </ul>
      )}
      <ButtonLink
        to={findAnotherVenuePath(reference, arrangement)}
        variant="secondary"
        aria-label={`Find another venue for ${arrangement.purpose}`}
      >
        Find another venue
      </ButtonLink>
    </section>
  )
}
