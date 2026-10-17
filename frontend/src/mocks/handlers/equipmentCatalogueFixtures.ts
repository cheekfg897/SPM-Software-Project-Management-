import { MOCK_EQUIPMENT_TYPES } from './equipmentFixtures'
import type { MockEquipmentType } from './equipmentFixtures'

/**
 * Data for the equipment catalogue mock (SCRUM-27, ADR-0014). Its types are the equipment mock's
 * (equipmentFixtures.ts), so every mock names the same things from one list.
 */

/** An equipment type as the backend returns it (EquipmentTypeSchema): not what the mock keeps free. */
export type MockCatalogueType = Omit<MockEquipmentType, 'free'>

/** Venues that exist in the mock, numbered as the catalogue and booking mocks number them. */
export const MOCK_VENUE_IDS: readonly number[] = [1, 2, 3, 4, 5, 6, 7, 8]

/**
 * The catalogue every mock run starts with: the equipment mock's types, saved in the opposite
 * order to the one the list shows them in (by name), so a list that kept the saved order would
 * show.
 */
export const MOCK_CATALOGUE_TYPES: readonly MockCatalogueType[] = MOCK_EQUIPMENT_TYPES.map(
  ({ id, name, description, total_quantity, venue_id, store_name }) => ({
    id,
    name,
    description,
    total_quantity,
    venue_id,
    store_name,
  }),
)
