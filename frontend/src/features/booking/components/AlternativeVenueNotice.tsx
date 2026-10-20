import { useId } from 'react'

import { ButtonLink } from '@/components/ui'
import { unavailabilityCategoryLabel } from '@/config/unavailabilityCategories'
import { formatDateTime } from '@/lib/formatDate'

import type { BookingRequest, Unavailability } from '../api'
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
 * Why a flagged arrangement needs an alternative venue: each block or deactivation the backend
 * lists, with its category, Venue Staff's note and its period in business time (SCRUM-92 AC1,
 * AC9), and a way to find another venue for its period (AC6). The arrangement itself is shown
 * above it as it was booked (AC4).
 */
export function AlternativeVenueNotice({ reference, arrangement }: AlternativeVenueNoticeProps) {
  const headingId = useId()

  return (
    <section
      aria-labelledby={headingId}
      className="border-danger/40 bg-danger/10 mt-3 space-y-2 rounded-xl border p-3"
    >
      <p id={headingId} className="text-danger font-medium">
        Needs an alternative venue
      </p>
      <ul aria-label="Why its venue is unavailable" className="text-ink space-y-1">
        {/* By place: two blocks may give the same reason for the same period. */}
        {arrangement.unavailability.map((cause, index) => (
          <li key={index}>
            {unavailabilityCategoryLabel(cause.category)}: {cause.reason}. Unavailable{' '}
            {periodText(cause)}.
          </li>
        ))}
      </ul>
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
