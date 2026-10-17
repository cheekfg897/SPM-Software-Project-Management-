import { apiRequest } from '@/lib/api'

/** The equipment catalogue API: backend/app/modules/equipment/routes.py (SCRUM-27, ADR-0014). */
const EQUIPMENT_CATALOGUE_PATHS = {
  TYPES: '/api/equipment/types',
  /** The id comes from the page's address, so it is escaped to stay one path segment. */
  type: (equipmentTypeId: string) => `/api/equipment/types/${encodeURIComponent(equipmentTypeId)}`,
} as const

/** One equipment type. It is kept at a venue or a store, never both, so one of the two is null. */
export interface EquipmentType {
  id: number
  name: string
  description: string | null
  total_quantity: number
  venue_id: number | null
  store_name: string | null
}

/**
 * What the form sends to add or change a type. Every field is sent; the backend checks them all
 * (an empty quantity or place goes as null, so it is refused rather than quietly kept).
 */
export interface EquipmentTypeInput {
  name: string
  description: string
  total_quantity: number | null
  venue_id: number | null
  store_name: string | null
}

export interface EquipmentTypeChange {
  equipmentTypeId: string
  changes: EquipmentTypeInput
}

export const equipmentCatalogueKeys = {
  all: ['equipmentCatalogue'] as const,
  list: () => [...equipmentCatalogueKeys.all, 'list'] as const,
  type: (equipmentTypeId: string) =>
    [...equipmentCatalogueKeys.all, 'type', equipmentTypeId] as const,
}

/** Every equipment type, in the backend's order (by name). */
export function fetchEquipmentTypes(): Promise<EquipmentType[]> {
  return apiRequest<EquipmentType[]>(EQUIPMENT_CATALOGUE_PATHS.TYPES)
}

export function fetchEquipmentType(equipmentTypeId: string): Promise<EquipmentType> {
  return apiRequest<EquipmentType>(EQUIPMENT_CATALOGUE_PATHS.type(equipmentTypeId))
}

/** Add a type to the catalogue. Technical Support Staff only. */
export function createEquipmentType(input: EquipmentTypeInput): Promise<EquipmentType> {
  return apiRequest<EquipmentType>(EQUIPMENT_CATALOGUE_PATHS.TYPES, { method: 'POST', body: input })
}

/** Change a type's fields. Technical Support Staff only. */
export function updateEquipmentType({
  equipmentTypeId,
  changes,
}: EquipmentTypeChange): Promise<EquipmentType> {
  return apiRequest<EquipmentType>(EQUIPMENT_CATALOGUE_PATHS.type(equipmentTypeId), {
    method: 'PATCH',
    body: changes,
  })
}
