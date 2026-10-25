import { REPLACEMENT_PARAMS } from '@/config/routes'
import { replacementSearchPath } from '@/features/venueSearch/searchParams'
import { businessDate, businessTimeOfDay } from '@/lib/formatDate'
import { positiveIdParam } from '@/lib/positiveIdParam'

import type { BookingRequest } from './api'

/**
 * Replacing a flagged arrangement (SCRUM-92 AC6): the venue search set to its period and needs,
 * and the replacement the request form raises, read from the page URL.
 */

/**
 * Whether the backend flagged the arrangement as needing another venue: its venue became
 * unavailable (SCRUM-92), or a significant change to the event flagged it (SCRUM-33 AC6).
 */
export function needsAnotherVenue(arrangement: BookingRequest): boolean {
  return arrangement.needs_alternative_venue || arrangement.flagged_after_change
}

/**
 * Whether a replacement for the arrangement keeps its date and times: it does while the
 * arrangement's venue is unavailable (SCRUM-92 AC6, Product Owner 25 Oct, ADR-0108). One flagged
 * only after a change to the event may move to a new period, as the backend allows (ADR-0100).
 */
export function keepsItsPeriod(replaced: BookingRequest | undefined): boolean {
  return replaced?.needs_alternative_venue === true
}

/** Find a venue, set to the flagged arrangement's period, occupancy and layout. */
export function findAnotherVenuePath(reference: string, arrangement: BookingRequest): string {
  const startDate = businessDate(arrangement.starts_at)
  const endDate = businessDate(arrangement.ends_at)
  return replacementSearchPath(
    { reference, arrangementId: arrangement.id, venueId: arrangement.venue_id },
    {
      date: startDate,
      start: businessTimeOfDay(arrangement.starts_at),
      end: businessTimeOfDay(arrangement.ends_at),
      end_date: endDate === startDate ? '' : endDate,
      min_capacity: String(arrangement.expected_occupancy),
      location: '',
      required_layout: arrangement.required_layout ?? '',
      required_facilities: [],
      required_accessibility: [],
    },
  )
}

/** The arrangement the request form replaces, and the venue chosen for it as typed. */
export interface ReplacementRequest {
  arrangementId: number
  venueId: string
}

/** The replacement in the URL, or null when the form raises an ordinary request. */
export function readReplacementRequest(params: URLSearchParams): ReplacementRequest | null {
  const arrangementId = positiveIdParam(params, REPLACEMENT_PARAMS.ARRANGEMENT)
  if (arrangementId === null) {
    return null
  }
  return { arrangementId, venueId: params.get(REPLACEMENT_PARAMS.VENUE) ?? '' }
}
