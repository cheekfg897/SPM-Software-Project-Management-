import type { EquipmentLine } from './api'
import { changedFields, EMPTY_LINE_VALUES, valuesOfLine } from './lineFormValues'

/** SCRUM-37 (ADR-0065): what the equipment line form sends. */

const LINE: EquipmentLine = {
  id: 58,
  equipment_type_id: 7,
  quantity: 12,
  notes: 'Two with wide lenses.',
  status: 'requested',
  provided_quantity: null,
  shortfall: null,
  outcome_note: null,
  reviewed_by: null,
  reviewed_at: null,
}

describe('SCRUM-37 equipment line form values', () => {
  it("holds a saved line's values as typed text, with no notes as an empty box", () => {
    expect(valuesOfLine(LINE)).toEqual({
      equipment_type_id: '7',
      quantity: '12',
      notes: 'Two with wide lenses.',
    })
    expect(valuesOfLine({ ...LINE, notes: null }).notes).toBe('')
  })

  it('sends what was filled in for a new line, as numbers where the backend wants them', () => {
    const values = { equipment_type_id: '3', quantity: '25', notes: 'By the stage' }

    expect(changedFields(values, EMPTY_LINE_VALUES)).toEqual({
      equipment_type_id: 3,
      quantity: 25,
      notes: 'By the stage',
    })
  })

  it('leaves out every field still blank on a new line', () => {
    expect(changedFields(EMPTY_LINE_VALUES, EMPTY_LINE_VALUES)).toEqual({})
  })

  it('sends only what changed on a saved line', () => {
    const original = valuesOfLine(LINE)

    expect(changedFields(original, original)).toEqual({})
    expect(changedFields({ ...original, quantity: '13' }, original)).toEqual({ quantity: 13 })
    expect(changedFields({ ...original, equipment_type_id: '9' }, original)).toEqual({
      equipment_type_id: 9,
    })
    expect(changedFields({ ...original, notes: '' }, original)).toEqual({ notes: '' })
  })

  it('sends a cleared number as null, for the backend to say why it is needed', () => {
    const original = valuesOfLine(LINE)

    expect(changedFields({ ...original, quantity: '', equipment_type_id: '' }, original)).toEqual({
      quantity: null,
      equipment_type_id: null,
    })
  })
})
