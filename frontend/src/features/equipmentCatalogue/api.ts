import { apiRequest } from '@/lib/api'

/** One type, by the id in the page's address, escaped so it stays one path segment. */
function typePath(equipmentTypeId: string): string {
  return `/api/equipment/types/${encodeURIComponent(equipmentTypeId)}`
}

/**
 * The equipment catalogue API: backend/app/modules/equipment/routes.py (SCRUM-27, ADR-0014), and
 * the units of a type out of service (SCRUM-47, ADR-0046).
 */
const EQUIPMENT_CATALOGUE_PATHS = {
  TYPES: '/api/equipment/types',
  type: typePath,
  outOfService: (equipmentTypeId: string) => `${typePath(equipmentTypeId)}/out-of-service`,
  returnToService: (entryId: number) => `/api/equipment/out-of-service/${entryId}/return`,
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

interface EquipmentTypeChange {
  equipmentTypeId: string
  changes: EquipmentTypeInput
}

/** Why units can't be used (SCRUM-47 AC1). Units not out of service are Available. */
export type OutOfServiceReason = 'damaged' | 'under_maintenance'

/**
 * Units of a type taken out of service, with who did it and when (AC4). People are named, null
 * once their account is gone; `resolved_by` and `resolved_at` stay null until the units are back.
 */
export interface OutOfServiceEntry {
  id: number
  equipment_type_id: number
  quantity: number
  reason: OutOfServiceReason
  recorded_by: string | null
  /** ISO date-time with an offset, in business time. */
  recorded_at: string
  resolved_by: string | null
  resolved_at: string | null
}

/** What taking units out sends. A blank field is left out, so the backend says what is missing. */
export interface OutOfServiceBody {
  quantity?: number
  reason?: OutOfServiceReason
}

interface OutOfServiceChange {
  equipmentTypeId: string
  body: OutOfServiceBody
}

export const equipmentCatalogueKeys = {
  all: ['equipmentCatalogue'] as const,
  list: () => [...equipmentCatalogueKeys.all, 'list'] as const,
  type: (equipmentTypeId: string) =>
    [...equipmentCatalogueKeys.all, 'type', equipmentTypeId] as const,
  /** Only Technical Support may read it, and it is the same for all of them. */
  outOfService: (equipmentTypeId: string) =>
    [...equipmentCatalogueKeys.type(equipmentTypeId), 'outOfService'] as const,
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

/** The type's units still out of service, oldest first. Technical Support Staff only. */
export function fetchOutOfService(equipmentTypeId: string): Promise<OutOfServiceEntry[]> {
  return apiRequest<OutOfServiceEntry[]>(EQUIPMENT_CATALOGUE_PATHS.outOfService(equipmentTypeId))
}

/** Take units of the type out of service. Technical Support Staff only. */
export function takeOutOfService({
  equipmentTypeId,
  body,
}: OutOfServiceChange): Promise<OutOfServiceEntry> {
  return apiRequest<OutOfServiceEntry>(EQUIPMENT_CATALOGUE_PATHS.outOfService(equipmentTypeId), {
    method: 'POST',
    body,
  })
}

/** Put an entry's units back in service, all of them at once. Technical Support Staff only. */
export function returnToService(entryId: number): Promise<OutOfServiceEntry> {
  return apiRequest<OutOfServiceEntry>(EQUIPMENT_CATALOGUE_PATHS.returnToService(entryId), {
    method: 'POST',
  })
}
