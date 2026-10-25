import { formatDateTime } from '@/lib/formatDate'

/**
 * Why a venue can't be used, as the backend names it (UnavailabilityCategory in
 * backend/app/modules/venue/models.py, SCRUM-92 AC2, ADR-0053). Venue Staff choose one when they
 * deactivate a venue, and a flagged booking carries one. The one list and type for every feature.
 */
export const UNAVAILABILITY_CATEGORIES = [
  { value: 'maintenance', label: 'Maintenance' },
  { value: 'equipment_failure', label: 'Equipment failure' },
  { value: 'renovation', label: 'Renovation' },
  { value: 'safety_concern', label: 'Safety concern' },
  { value: 'other', label: 'Other' },
] as const

export type UnavailabilityCategory = (typeof UNAVAILABILITY_CATEGORIES)[number]['value']

/** A category's words, e.g. "Equipment failure"; one the list doesn't know reads as sent. */
export function unavailabilityCategoryLabel(category: string): string {
  const known = UNAVAILABILITY_CATEGORIES.find((each) => each.value === category)
  return known?.label ?? category
}

/** A block or deactivation that made a venue unavailable, as the backend sends it (SCRUM-92). */
export interface UnavailabilityCause {
  category: string
  /** Venue Staff's note. */
  reason: string
  /** ISO date-times in business time; `ends_at` is null until a deactivated venue is reactivated. */
  starts_at: string
  ends_at: string | null
}

/** e.g. "from 26 Nov, 8:00 am to 26 Nov, 6:00 pm"; a deactivation has no end yet. */
function periodText(cause: UnavailabilityCause): string {
  const from = `from ${formatDateTime(cause.starts_at)}`
  if (cause.ends_at === null) {
    return `${from} until the venue is reactivated`
  }
  return `${from} to ${formatDateTime(cause.ends_at)}`
}

/**
 * Why a venue is unavailable, in one sentence: its category, Venue Staff's note and the period in
 * business time (SCRUM-92 AC1, AC9), wherever a flagged arrangement is shown.
 */
export function unavailabilityText(cause: UnavailabilityCause): string {
  return `${unavailabilityCategoryLabel(cause.category)}: ${cause.reason}. Unavailable ${periodText(cause)}.`
}
