import { inputFromForm } from './equipmentTypeForm'

/** A form with these fields filled in, as the browser would collect it. */
function formWith(fields: Record<string, string>): FormData {
  const form = new FormData()
  for (const [name, value] of Object.entries(fields)) {
    form.set(name, value)
  }
  return form
}

const FILLED = {
  name: ' Lectern ',
  description: ' Oak. ',
  total_quantity: '2',
  venue_id: '',
  store_name: ' Jurong store ',
}

describe('SCRUM-27 the equipment type form', () => {
  it('sends every field as typed, the numbers as numbers', () => {
    expect(inputFromForm(formWith({ ...FILLED, venue_id: '7', store_name: '' }))).toEqual({
      name: ' Lectern ',
      description: ' Oak. ',
      total_quantity: 2,
      venue_id: 7,
      store_name: null,
    })
  })

  it('sends an empty quantity, venue or store as null, and an empty description as empty', () => {
    expect(
      inputFromForm(
        formWith({ name: '', description: '', total_quantity: '', venue_id: '', store_name: '' }),
      ),
    ).toEqual({ name: '', description: '', total_quantity: null, venue_id: null, store_name: null })
  })

  it('leaves a quantity that is not whole for the backend to refuse', () => {
    expect(inputFromForm(formWith({ ...FILLED, total_quantity: '1.5' })).total_quantity).toBe(1.5)
  })

  it('keeps a store name of spaces, so the backend says it is blank', () => {
    expect(inputFromForm(formWith({ ...FILLED, store_name: '  ' })).store_name).toBe('  ')
  })
})
