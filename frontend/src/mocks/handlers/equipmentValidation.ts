/**
 * The backend's wording for the numbers an equipment body carries (app/common/fields.py), shared
 * by the reservation and equipment line mocks.
 */

export const MISSING_MESSAGE = 'Missing data for required field.'
export const EQUIPMENT_TYPE_ID_RANGE_MESSAGE = 'equipment_type_id must be a positive number.'
export const QUANTITY_RANGE_MESSAGE = 'Quantity must be at least 1.'

/**
 * What is wrong with a sent whole number of at least 1 (PositiveId, PositiveQuantity), or
 * undefined when nothing is. A JSON boolean is not a number to the backend.
 */
export function positiveWholeNumberError(value: unknown, rangeMessage: string): string | undefined {
  if (value === null) {
    return 'Field may not be null.'
  }
  if (typeof value !== 'number' || !Number.isInteger(value)) {
    return 'Not a valid integer.'
  }
  if (value < 1) {
    return rangeMessage
  }
  return undefined
}
