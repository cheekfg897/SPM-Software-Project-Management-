import type { EquipmentLine } from './api'

/** A line Technical Support have recorded an outcome for (SCRUM-48). */
export interface ReviewedLine extends EquipmentLine {
  provided_quantity: number
  shortfall: number
  reviewed_at: string
}

/**
 * Whether the line has an outcome. The backend sets the quantity provided, the shortfall and the
 * review time together and clears none of them (ADR-0040), so the quantity tells for all three.
 */
export function hasOutcome(line: EquipmentLine): line is ReviewedLine {
  return line.provided_quantity !== null
}
