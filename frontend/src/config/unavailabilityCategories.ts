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
