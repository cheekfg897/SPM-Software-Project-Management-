import { locationText } from './locationText'

const LECTERN = { id: 4, name: 'Lectern', description: null, total_quantity: 2 }

describe('SCRUM-27 where an equipment type is kept, in words', () => {
  it('names a venue by its number', () => {
    expect(locationText({ ...LECTERN, venue_id: 7, store_name: null })).toBe('Venue 7')
  })

  it('names a store by its name', () => {
    expect(locationText({ ...LECTERN, venue_id: null, store_name: 'Jurong store' })).toBe(
      'Store: Jurong store',
    )
  })
})
