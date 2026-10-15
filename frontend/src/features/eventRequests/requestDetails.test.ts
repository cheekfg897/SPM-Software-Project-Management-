import { detailsFromForm } from './requestDetails'

function formWith(values: Record<string, string>): FormData {
  const form = new FormData()
  for (const [name, value] of Object.entries(values)) {
    form.set(name, value)
  }
  return form
}

describe('SCRUM-19 detailsFromForm', () => {
  it('sends every field filled in, the attendance as a number and the times as typed', () => {
    const form = formWith({
      name: 'Harbour Lights Gala',
      purpose: 'Fundraiser',
      description: 'An evening on the water.',
      proposed_date: '2026-11-20',
      end_date: '2026-11-21',
      start_time: '19:00',
      end_time: '02:00',
      expected_attendance: '300',
      venue_requirements: 'Waterfront',
      accessibility_needs: 'Step-free access',
      equipment_requirements: 'Two microphones',
    })

    expect(detailsFromForm(form, true)).toEqual({
      name: 'Harbour Lights Gala',
      purpose: 'Fundraiser',
      description: 'An evening on the water.',
      proposed_date: '2026-11-20',
      end_date: '2026-11-21',
      start_time: '19:00',
      end_time: '02:00',
      expected_attendance: 300,
      venue_requirements: 'Waterfront',
      accessibility_needs: 'Step-free access',
      equipment_requirements: 'Two microphones',
      registration_required: true,
    })
  })

  it('leaves out every field left empty, so the backend can say which it needs', () => {
    const form = formWith({
      name: 'Just a name',
      purpose: '',
      proposed_date: '',
      expected_attendance: '',
    })

    expect(detailsFromForm(form, false)).toEqual({
      name: 'Just a name',
      registration_required: false,
    })
  })
})
