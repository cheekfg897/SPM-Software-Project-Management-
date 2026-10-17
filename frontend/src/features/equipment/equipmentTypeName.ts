import type { EquipmentType } from './api'

/**
 * An equipment type's name from the catalogue. Lines carry only the type's id (ADR-0019); one the
 * catalogue no longer lists is named by that id rather than left blank.
 */
export function equipmentTypeName(
  equipmentTypes: EquipmentType[],
  equipmentTypeId: number,
): string {
  const equipmentType = equipmentTypes.find((candidate) => candidate.id === equipmentTypeId)
  if (equipmentType === undefined) {
    return `Equipment type ${equipmentTypeId}`
  }
  return equipmentType.name
}
