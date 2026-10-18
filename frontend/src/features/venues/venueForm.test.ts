import { listFieldErrors, periodFieldErrors, venueFromForm } from './venueForm'

/** A FormData holding these fields; a list value is a field sent several times. */
function formWith(fields: Record<string, string | string[]>): FormData {
  const form = new FormData()
  for (const [name, value] of Object.entries(fields)) {
    for (const each of Array.isArray(value) ? value : [value]) {
      form.append(name, each)
    }
  }
  return form
}

const FILLED_IN = {
  name: ' Skyline Room ',
  location: 'Level 9',
  capacity: '64',
  facilities: 'Projector\n\n  \nStage ',
  accessibility_features: '',
  supported_layouts: ['theatre', 'banquet'],
  setup_minutes: '15',
  turnaround_minutes: '0',
  'opening_hours.0.open.day': 'friday',
  'opening_hours.0.open.time': '18:00',
  'opening_hours.0.close.day': 'saturday',
  'opening_hours.0.close.time': '02:00',
  'opening_hours.1.open.day': 'monday',
  'opening_hours.1.open.time': '09:00',
  'opening_hours.1.close.day': 'monday',
  'opening_hours.1.close.time': '',
}

describe('SCRUM-25 what the venue form sends', () => {
  it('sends every field as typed, the lists one item per non-empty line and the hours row by row', () => {
    expect(venueFromForm(formWith(FILLED_IN))).toEqual({
      name: ' Skyline Room ',
      location: 'Level 9',
      capacity: 64,
      facilities: ['Projector', 'Stage '],
      accessibility_features: [],
      supported_layouts: ['theatre', 'banquet'],
      setup_minutes: 15,
      turnaround_minutes: 0,
      opening_hours: [
        { open: { day: 'friday', time: '18:00' }, close: { day: 'saturday', time: '02:00' } },
        { open: { day: 'monday', time: '09:00' }, close: { day: 'monday', time: '' } },
      ],
    })
  })

  it('sends an empty capacity as null, so the backend refuses it (ADR-0067)', () => {
    const details = venueFromForm(formWith({ ...FILLED_IN, capacity: '' }))

    expect(details.capacity).toBeNull()
  })

  it('leaves out an empty setup or turnaround time, so the backend keeps or picks its own (SCRUM-67 AC2)', () => {
    const details = venueFromForm(
      formWith({ ...FILLED_IN, setup_minutes: '', turnaround_minutes: '' }),
    )

    expect(details).not.toHaveProperty('setup_minutes')
    expect(details).not.toHaveProperty('turnaround_minutes')
  })

  it('sends no layouts and no hours when none are chosen', () => {
    const details = venueFromForm(
      formWith({ name: 'Bare', location: 'Nowhere', capacity: '5', facilities: 'Stage' }),
    )

    expect(details).toMatchObject({ supported_layouts: [], opening_hours: [] })
  })
})

describe('SCRUM-25 where the backend messages go on the venue form', () => {
  it("puts a list's own messages first, then each item's, numbered from 1", () => {
    const fieldErrors = {
      'facilities.1': ['Items cannot contain ",".'],
      facilities: ['At most 9 items are allowed.'],
      'facilities.0': ['Items cannot be blank.', 'Items must be at most 50 characters.'],
      'accessibility_features.0': ['Items cannot be blank.'],
      facilities_note: ['Unknown field.'],
    }

    expect(listFieldErrors(fieldErrors, 'facilities')).toEqual([
      'At most 9 items are allowed.',
      'Item 2: Items cannot contain ",".',
      'Item 1: Items cannot be blank.',
      'Item 1: Items must be at most 50 characters.',
    ])
  })

  it('has nothing for a list the backend did not mention', () => {
    expect(listFieldErrors({ name: ['Must not be blank.'] }, 'facilities')).toEqual([])
  })

  it('gives each control of a period its own messages, and the period the ones about it all', () => {
    const fieldErrors = {
      'opening_hours.1.open.day': ['Must be one of: monday.'],
      'opening_hours.1.open.time': ['Not a valid time.'],
      'opening_hours.1.close.day': ['Not a valid day.'],
      'opening_hours.1.close.time': ['Not a valid time.'],
      'opening_hours.1.close': ['An opening period cannot be longer than 24 hours.'],
      'opening_hours.1': ['Overlaps opening period 0.'],
      'opening_hours.0.close': ['Close time must be after open time.'],
      'opening_hours.11': ['Overlaps opening period 3.'],
    }

    expect(periodFieldErrors(fieldErrors, 1)).toEqual({
      openDay: ['Must be one of: monday.'],
      openTime: ['Not a valid time.'],
      closeDay: ['Not a valid day.'],
      closeTime: ['Not a valid time.', 'An opening period cannot be longer than 24 hours.'],
      period: ['Overlaps opening period 0.'],
    })
  })

  it('has no messages for a period the backend did not mention', () => {
    expect(periodFieldErrors({ 'opening_hours.0': ['Overlaps opening period 1.'] }, 2)).toEqual({
      openDay: [],
      openTime: [],
      closeDay: [],
      closeTime: [],
      period: [],
    })
  })
})
