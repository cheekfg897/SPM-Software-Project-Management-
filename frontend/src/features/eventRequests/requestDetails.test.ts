import { changesFromForm, detailsFromForm } from './requestDetails'

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

describe('SCRUM-20 changesFromForm', () => {
  it('sends every field, an emptied one as null so the draft forgets it', () => {
    const form = formWith({
      name: 'Spring Fair',
      purpose: '',
      description: 'Stalls and music.',
      proposed_date: '2026-11-20',
      end_date: '',
      start_time: '10:00',
      end_time: '',
      expected_attendance: '',
      venue_requirements: '',
      accessibility_needs: '',
      equipment_requirements: '',
    })

    expect(changesFromForm(form, false)).toEqual({
      name: 'Spring Fair',
      purpose: null,
      description: 'Stalls and music.',
      proposed_date: '2026-11-20',
      end_date: null,
      start_time: '10:00',
      end_time: null,
      expected_attendance: null,
      venue_requirements: null,
      accessibility_needs: null,
      equipment_requirements: null,
      registration_required: false,
    })
  })

  it('sends the attendance as a number', () => {
    const form = formWith({ name: 'Spring Fair', expected_attendance: '80' })

    expect(changesFromForm(form, true)).toMatchObject({
      expected_attendance: 80,
      registration_required: true,
    })
  })
})
