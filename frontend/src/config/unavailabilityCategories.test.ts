import { unavailabilityCategoryLabel, unavailabilityText } from './unavailabilityCategories'

describe('SCRUM-92 unavailabilityCategoryLabel', () => {
  it('words a category the backend names', () => {
    expect(unavailabilityCategoryLabel('equipment_failure')).toBe('Equipment failure')
  })

  it('shows a category it does not know as the backend sent it', () => {
    expect(unavailabilityCategoryLabel('flooding')).toBe('flooding')
  })
})

describe('SCRUM-92 unavailabilityText', () => {
  it('words a block with its category, note and period in business time', () => {
    const block = {
      category: 'maintenance',
      reason: 'Roof repairs',
      starts_at: '2026-11-26T08:00:00+08:00',
      ends_at: '2026-11-26T18:00:00+08:00',
    }

    expect(unavailabilityText(block)).toBe(
      'Maintenance: Roof repairs. Unavailable from 26 Nov, 8:00 am to 26 Nov, 6:00 pm.',
    )
  })

  it('says a deactivation lasts until the venue is reactivated', () => {
    const deactivation = {
      category: 'renovation',
      reason: 'Closed for refit',
      starts_at: '2026-11-01T12:00:00+08:00',
      ends_at: null,
    }

    expect(unavailabilityText(deactivation)).toBe(
      'Renovation: Closed for refit. Unavailable from 1 Nov, 12:00 pm until the venue is reactivated.',
    )
  })
})
