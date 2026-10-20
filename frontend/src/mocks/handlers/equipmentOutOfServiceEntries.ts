/**
 * The units of each equipment type out of service (SCRUM-47), kept in memory until
 * resetMockOutOfService. A file of its own so both the out-of-service routes and the
 * availability and reservation routes (equipment.ts) can read it without importing each other.
 */

export interface MockOutOfServiceEntry {
  id: number
  equipment_type_id: number
  quantity: number
  reason: string
  recorded_by: string
  recorded_at: string
  resolved_by: string | null
  resolved_at: string | null
}

let entries: MockOutOfServiceEntry[] = []

/** Put every unit back in service and start the ids again. Runs with resetMockEquipment. */
export function resetMockOutOfService(): void {
  entries = []
}

/** Save a new entry, with the next id. */
export function addOutOfServiceEntry(
  entry: Omit<MockOutOfServiceEntry, 'id'>,
): MockOutOfServiceEntry {
  const saved = { id: entries.length + 1, ...entry }
  entries.push(saved)
  return saved
}

/** The entry with this id, still out or put back. */
export function outOfServiceEntry(entryId: number): MockOutOfServiceEntry | undefined {
  return entries.find((candidate) => candidate.id === entryId)
}

/** The type's entries not yet put back, oldest first: ids follow the order they were recorded. */
export function entriesStillOut(equipmentTypeId: number): MockOutOfServiceEntry[] {
  return entries.filter(
    (entry) => entry.equipment_type_id === equipmentTypeId && entry.resolved_at === null,
  )
}

/** How many units of the type are out of service now: every entry not yet put back. */
export function outOfServiceQuantity(equipmentTypeId: number): number {
  let total = 0
  for (const entry of entriesStillOut(equipmentTypeId)) {
    total += entry.quantity
  }
  return total
}
