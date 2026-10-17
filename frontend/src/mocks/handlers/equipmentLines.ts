import { MOCK_EQUIPMENT_LINES } from './equipmentFixtures'
import type { MockEquipmentLine } from './equipmentFixtures'

/**
 * Each event's equipment lines (SCRUM-37), kept in memory in the order they were added, as the
 * backend lists them. The equipment mock reads them for availability's "requested".
 */

let lines: MockEquipmentLine[] = []

/** Put every event's lines back as they started. Runs after every test. */
export function resetMockEquipmentLines(): void {
  lines = MOCK_EQUIPMENT_LINES.map((line) => ({ ...line }))
}

resetMockEquipmentLines()

/** The event's lines, in the order they were added. */
export function linesOfEvent(reference: string): MockEquipmentLine[] {
  return lines.filter((line) => line.event_reference === reference)
}

/** How many units of the type the event asks for: its line's quantity, or 0 without one. */
export function requestedQuantity(reference: string, equipmentTypeId: number): number {
  const line = linesOfEvent(reference).find(
    (candidate) => candidate.equipment_type_id === equipmentTypeId,
  )
  return line === undefined ? 0 : line.quantity
}
