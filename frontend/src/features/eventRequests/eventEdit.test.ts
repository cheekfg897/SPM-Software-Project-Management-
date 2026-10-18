import type { EventRecord } from './api'
import { changedFields } from './eventEdit'

/**
 * SCRUM-33 AC1, AC2: what the coordinator's edit form sends. Only what differs from the record
 * goes, so a date moved on its own lets the backend move the end date with it, and a field left
 * as it was is never sent (ADR-0025, ADR-0079).
 */

const RECORD: EventRecord = {
  reference: 'EVR-7K2M9QXA',
  status: 'under_review',
  name: 'Partner Summit',
  purpose: 'Meet our partners.',
  description: null,
  proposed_date: '2026-11-12',
  end_date: '2026-11-12',
  start_time: '09:00:00',
  end_time: '17:00:00',
  expected_attendance: 250,
  venue_requirements: 'A main hall for 250.',
  accessibility_needs: null,
  equipment_requirements: null,
  registration_required: false,
  created_at: '2026-10-06T02:00:00+00:00',
  programme_notes: 'Keynote at 9:30.',
  coordinator: null,
  decision: null,
  clarifications: [],
}

/** The form as it opens on RECORD, with `typed` changed. */
function formWith(typed: Record<string, string> = {}): FormData {
  const values: Record<string, string> = {
    description: '',
    programme_notes: 'Keynote at 9:30.',
    accessibility_needs: '',
    internal_planning_notes: '',
    proposed_date: '2026-11-12',
    end_date: '2026-11-12',
    start_time: '09:00',
    end_time: '17:00',
    expected_attendance: '250',
    venue_requirements: 'A main hall for 250.',
    equipment_requirements: '',
    ...typed,
  }
  const form = new FormData()
  for (const [name, value] of Object.entries(values)) {
    form.set(name, value)
  }
  return form
}

describe('SCRUM-33 what the edit form sends', () => {
  it('sends nothing when nothing was changed', () => {
    expect(changedFields(formWith(), RECORD)).toEqual({})
  })

  it('sends each text field that changed, and an emptied one as null', () => {
    const form = formWith({
      description: 'Two days with our partners.',
      programme_notes: '',
      venue_requirements: 'A main hall for 300.',
    })

    expect(changedFields(form, RECORD)).toEqual({
      description: 'Two days with our partners.',
      programme_notes: null,
      venue_requirements: 'A main hall for 300.',
    })
  })

  it('sends accessibility and equipment needs that were added', () => {
    const form = formWith({ accessibility_needs: 'Step-free', equipment_requirements: 'Mics' })

    expect(changedFields(form, RECORD)).toEqual({
      accessibility_needs: 'Step-free',
      equipment_requirements: 'Mics',
    })
  })

  it('sends a moved date without the end date, so the backend keeps the length (ADR-0025)', () => {
    expect(changedFields(formWith({ proposed_date: '2026-11-19' }), RECORD)).toEqual({
      proposed_date: '2026-11-19',
    })
  })

  it('sends a changed end date, time and attendance, the attendance as a number', () => {
    const form = formWith({
      end_date: '2026-11-13',
      start_time: '10:30',
      end_time: '18:00',
      expected_attendance: '300',
    })

    expect(changedFields(form, RECORD)).toEqual({
      end_date: '2026-11-13',
      start_time: '10:30',
      end_time: '18:00',
      expected_attendance: 300,
    })
  })

  it('sends an emptied date, time or attendance as null, for the backend to refuse', () => {
    const form = formWith({ proposed_date: '', start_time: '', expected_attendance: '' })

    expect(changedFields(form, RECORD)).toEqual({
      proposed_date: null,
      start_time: null,
      expected_attendance: null,
    })
  })

  it('sends internal planning notes only when some are typed, since the record has none to show', () => {
    expect(changedFields(formWith({ internal_planning_notes: 'Call AV.' }), RECORD)).toEqual({
      internal_planning_notes: 'Call AV.',
    })
    expect(changedFields(formWith({ internal_planning_notes: '' }), RECORD)).toEqual({})
  })

  it('compares an attendance of six digits whole', () => {
    const record = { ...RECORD, expected_attendance: 123456 }

    expect(changedFields(formWith({ expected_attendance: '123456' }), record)).toEqual({})
  })

  it('compares a record that has no time or attendance yet with an empty field', () => {
    const record = { ...RECORD, start_time: null, expected_attendance: null }
    const form = formWith({ start_time: '', expected_attendance: '' })

    expect(changedFields(form, record)).toEqual({})
  })
})
