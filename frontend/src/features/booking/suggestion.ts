import { SUGGESTION_PARAM } from '@/config/routes'
import { formatShortDate, formatTimeRange } from '@/lib/formatDate'
import { positiveIdParam } from '@/lib/positiveIdParam'

/**
 * The alternative Venue Staff may suggest when they reject a request (SCRUM-70, ADR-0123): how it
 * reads beside the reason, and the rejected request the request form starts from.
 */

const SAME_VENUE = 'The same venue'
const SAME_PERIOD = 'the same period'

/**
 * A suggestion in words, e.g. "Garden Pavilion · 26 Nov, 1:00 pm – 5:00 pm", with the venue as the
 * caller names it. A part not suggested reads as the same venue or the same period. Null when
 * nothing was suggested.
 */
export function suggestionText(
  venue: string | null,
  startsAt: string | null,
  endsAt: string | null,
): string | null {
  const hasPeriod = startsAt !== null && endsAt !== null
  if (venue === null && !hasPeriod) {
    return null
  }
  const where = venue ?? SAME_VENUE
  const when = hasPeriod
    ? `${formatShortDate(startsAt)}, ${formatTimeRange(startsAt, endsAt)}`
    : SAME_PERIOD
  return `${where} · ${when}`
}

/** The rejected request the form starts from, from the page URL, or null for none. */
export function readSuggestionId(params: URLSearchParams): number | null {
  return positiveIdParam(params, SUGGESTION_PARAM)
}
