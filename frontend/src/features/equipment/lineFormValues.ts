import type { EquipmentLine, EquipmentLineBody } from './api'

/** What the equipment line form holds: each field as typed. */
export interface LineFormValues {
  /** The chosen type's id, or '' while none is chosen. */
  equipment_type_id: string
  quantity: string
  notes: string
}

export const EMPTY_LINE_VALUES: LineFormValues = { equipment_type_id: '', quantity: '', notes: '' }

/** A saved line's values, ready to change. Notes it doesn't have are an empty box. */
export function valuesOfLine(line: EquipmentLine): LineFormValues {
  return {
    equipment_type_id: String(line.equipment_type_id),
    quantity: String(line.quantity),
    notes: line.notes ?? '',
  }
}

/** A number field as the backend reads it: null once it has been cleared. */
function numberOrNull(typed: string): number | null {
  if (typed === '') {
    return null
  }
  return Number(typed)
}

/**
 * The fields that differ from `original`, for the backend to check (ADR-0050). Adding compares
 * with the empty form, so a field left blank isn't sent and the backend says it is missing; a
 * change sends only the fields that were touched.
 */
export function changedFields(values: LineFormValues, original: LineFormValues): EquipmentLineBody {
  const body: EquipmentLineBody = {}
  if (values.equipment_type_id !== original.equipment_type_id) {
    body.equipment_type_id = numberOrNull(values.equipment_type_id)
  }
  if (values.quantity !== original.quantity) {
    body.quantity = numberOrNull(values.quantity)
  }
  if (values.notes !== original.notes) {
    body.notes = values.notes
  }
  return body
}
