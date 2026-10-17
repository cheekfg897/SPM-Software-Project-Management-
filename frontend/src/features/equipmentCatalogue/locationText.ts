import type { EquipmentType } from './api'

/**
 * Where a type is kept, in words. The backend keeps it at a venue or a store, never both
 * (ADR-0014), and sends a venue's id rather than its name (ADR-0054).
 */
export function locationText({ venue_id: venueId, store_name: storeName }: EquipmentType): string {
  if (storeName !== null) {
    return `Store: ${storeName}`
  }
  return `Venue ${String(venueId)}`
}
