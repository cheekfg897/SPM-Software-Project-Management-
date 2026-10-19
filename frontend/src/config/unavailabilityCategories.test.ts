import { unavailabilityCategoryLabel } from './unavailabilityCategories'

describe('SCRUM-92 unavailabilityCategoryLabel', () => {
  it('words a category the backend names', () => {
    expect(unavailabilityCategoryLabel('equipment_failure')).toBe('Equipment failure')
  })

  it('shows a category it does not know as the backend sent it', () => {
    expect(unavailabilityCategoryLabel('flooding')).toBe('flooding')
  })
})
