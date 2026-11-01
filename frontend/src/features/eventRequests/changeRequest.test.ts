import { describeRequestedChange, requestedChange } from './changeRequest'
import { formWith, RECORD } from './test/recordForm'

/**
 * SCRUM-56 AC2: what the organiser's change request form sends, and how a requested change is
 * worded on the record. Only the event's date, times, attendance, venue and equipment
 * requirements and programme notes can be asked for, and only those that differ from the record
 * are sent, with why (ADR-0126).
 */

describe('SCRUM-56 AC2 what the change request form sends', () => {
  it('sends only why when nothing was changed, for the backend to say what is missing', () => {
    const form = formWith({ reason: 'Our keynote speaker lands late.' })

    expect(requestedChange(form, RECORD)).toEqual({ reason: 'Our keynote speaker lands late.' })
  })

  it('sends each requestable field that changed, the attendance as a number', () => {
    const form = formWith({
      reason: 'More partners said yes.',
      proposed_date: '2026-11-19',
      start_time: '10:00',
      expected_attendance: '300',
      venue_requirements: 'A main hall for 300.',
      equipment_requirements: 'Two more microphones.',
      programme_notes: 'Keynote at 10:30.',
    })

    expect(requestedChange(form, RECORD)).toEqual({
      reason: 'More partners said yes.',
      proposed_date: '2026-11-19',
      start_time: '10:00',
      expected_attendance: 300,
      venue_requirements: 'A main hall for 300.',
      equipment_requirements: 'Two more microphones.',
      programme_notes: 'Keynote at 10:30.',
    })
  })

  it('sends an emptied requirement as null, asking for it to be cleared', () => {
    const form = formWith({ reason: 'We bring our own.', venue_requirements: '' })

    expect(requestedChange(form, RECORD)).toEqual({
      reason: 'We bring our own.',
      venue_requirements: null,
    })
  })

  it('never sends a detail a change request cannot ask for, even when it differs', () => {
    const form = formWith({ reason: 'Why not.', description: 'New words.', end_date: '2026-11-13' })

    expect(requestedChange(form, RECORD)).toEqual({ reason: 'Why not.', end_date: '2026-11-13' })
  })
})

describe('SCRUM-56 AC4 a requested change in words', () => {
  it('names the field and shows its value when raised beside the one asked for', () => {
    const change = { field: 'start_time', previous_value: '09:00:00', requested_value: '10:30:00' }

    expect(describeRequestedChange(change)).toEqual({
      label: 'Start time',
      value: '9:00 am → 10:30 am',
    })
  })

  it('says a value was not set, either side', () => {
    const added = { field: 'equipment_requirements', previous_value: null, requested_value: 'Mics' }
    const cleared = { field: 'programme_notes', previous_value: 'Keynote', requested_value: null }

    expect(describeRequestedChange(added)).toEqual({
      label: 'Equipment requirements',
      value: 'Not set → Mics',
    })
    expect(describeRequestedChange(cleared)).toEqual({
      label: 'Programme notes',
      value: 'Keynote → Not set',
    })
  })

  it('shows a date as a day and an attendance as its number', () => {
    const moved = {
      field: 'proposed_date',
      previous_value: '2026-11-12',
      requested_value: '2026-11-19',
    }
    const grown = { field: 'expected_attendance', previous_value: 250, requested_value: 300 }

    expect(describeRequestedChange(moved).value).toBe('Thu, 12 Nov → Thu, 19 Nov')
    expect(describeRequestedChange(grown)).toEqual({
      label: 'Expected attendance',
      value: '250 → 300',
    })
  })
})
