import { describeHistoryEntry, EVENT_HISTORY_KIND } from './eventHistory'
import type { DescribedEntry } from './eventHistory'

/**
 * SCRUM-33 AC4, AC5: each kind of history entry the backend writes, in plain English, with
 * what its `details` say (ADR-0025, ADR-0076). The details are written as the backend sends
 * them: names, never ids, and dates and times as it stores them.
 */

/** An entry that is not a significant change, with these facts as [label, value] pairs. */
function plain(title: string, facts: [string, string][] = []): DescribedEntry {
  return { title, isSignificant: false, facts: facts.map(([label, value]) => ({ label, value })) }
}

function described(kind: string, details: Record<string, unknown> = {}): DescribedEntry {
  return describeHistoryEntry({ kind, details })
}

const SAFETY_CHECKLIST = {
  attendance_vs_capacity: '80 expected in a hall for 120.',
  venue_layout: 'Theatre layout, two aisles.',
  emergency_access: 'Both fire exits clear.',
  accessibility: 'Ramp at the side entrance.',
  equipment_placement: 'Cables taped down along the stage.',
  crowd_movement: 'One-way flow at the doors.',
  venue_restrictions: 'No open flames.',
}

describe('SCRUM-33 the kinds of history entry', () => {
  it('knows every kind the backend writes today (EventHistoryKind in events/models.py)', () => {
    expect(Object.values(EVENT_HISTORY_KIND).sort()).toEqual([
      'clarification_answered',
      'clarification_requested',
      'coordinator_assigned',
      'coordinator_reassigned',
      'decision_recorded',
      'equipment_outcome_recorded',
      'equipment_preparation_updated',
      'equipment_reserved',
      'event_completed',
      'event_confirmed',
      'field_changed',
      'review_started',
      'safety_outcome_recorded',
      'safety_review_requested',
      'venue_arrangement_changed',
      'venue_arrangement_withdrawn',
      'venue_booking_approved',
      'venue_booking_rejected',
      'venue_booking_requested',
      'venue_preparation_updated',
    ])
  })
})

describe('SCRUM-33 describing who looks after the event', () => {
  it('names the coordinator who was assigned', () => {
    expect(described('coordinator_assigned', { coordinator_name: 'Chloe Lim' })).toEqual(
      plain('Coordinator assigned', [['Coordinator', 'Chloe Lim']]),
    )
  })

  it('leaves out a coordinator whose account is gone', () => {
    expect(described('coordinator_assigned', { coordinator_name: null })).toEqual(
      plain('Coordinator assigned'),
    )
  })

  it('names both coordinators of a reassignment, as they were called then', () => {
    const details = { previous_coordinator_name: 'Chloe Lim', coordinator_name: 'Aisha Karim' }

    expect(described('coordinator_reassigned', details)).toEqual(
      plain('Coordinator changed', [
        ['From', 'Chloe Lim'],
        ['To', 'Aisha Karim'],
      ]),
    )
  })
})

describe('SCRUM-33 AC4 describing a changed field', () => {
  it('names the field and gives its value before and after', () => {
    const details = {
      field: 'programme_notes',
      previous_value: 'Keynote at 9:00.',
      new_value: 'Keynote at 9:30.',
      significant: false,
    }

    expect(described('field_changed', details)).toEqual(
      plain('Programme notes changed', [
        ['Before', 'Keynote at 9:00.'],
        ['After', 'Keynote at 9:30.'],
      ]),
    )
  })

  it('marks a significant change (AC2)', () => {
    const details = {
      field: 'expected_attendance',
      previous_value: 200,
      new_value: 250,
      significant: true,
    }

    expect(described('field_changed', details)).toEqual({
      ...plain('Expected attendance changed', [
        ['Before', '200'],
        ['After', '250'],
      ]),
      isSignificant: true,
    })
  })

  it('shows a date as a day and a time as a time, as the record does', () => {
    const date = {
      field: 'proposed_date',
      previous_value: '2026-11-12',
      new_value: '2026-11-19',
      significant: true,
    }
    const time = { field: 'start_time', previous_value: '09:00:00', new_value: '13:30:00' }

    expect(described('field_changed', date).facts).toEqual([
      { label: 'Before', value: 'Thu, 12 Nov' },
      { label: 'After', value: 'Thu, 19 Nov' },
    ])
    expect(described('field_changed', time).facts).toEqual([
      { label: 'Before', value: '9:00 am' },
      { label: 'After', value: '1:30 pm' },
    ])
  })

  it('shows the end date and end time the same way', () => {
    const date = { field: 'end_date', previous_value: '2026-11-12', new_value: '2026-11-13' }
    const time = { field: 'end_time', previous_value: '17:00:00', new_value: '18:15:00' }

    expect(described('field_changed', date).facts.map((fact) => fact.value)).toEqual([
      'Thu, 12 Nov',
      'Fri, 13 Nov',
    ])
    expect(described('field_changed', time).facts.map((fact) => fact.value)).toEqual([
      '5:00 pm',
      '6:15 pm',
    ])
  })

  it('names the withdrawal cut-off and shows it as a day and time in Singapore (SCRUM-69 AC7)', () => {
    const recorded = {
      field: 'withdrawal_cut_off',
      previous_value: null,
      new_value: '2026-10-04T18:00:00+08:00',
    }
    const moved = {
      field: 'withdrawal_cut_off',
      previous_value: '2026-10-04T18:00:00+08:00',
      new_value: '2026-10-03T01:30:00Z',
    }

    expect(described('field_changed', recorded)).toEqual(
      plain('Withdrawal cut-off changed', [
        ['Before', 'Not set'],
        ['After', '4 Oct, 6:00 pm'],
      ]),
    )
    expect(described('field_changed', moved).facts.map((fact) => fact.value)).toEqual([
      '4 Oct, 6:00 pm',
      '3 Oct, 9:30 am',
    ])
  })

  it('says a value was not set, and gives a yes or no for a setting', () => {
    const notes = { field: 'internal_planning_notes', previous_value: null, new_value: 'Call AV.' }
    const setting = { field: 'registration_enabled', previous_value: false, new_value: true }

    expect(described('field_changed', notes)).toEqual(
      plain('Planning notes changed', [
        ['Before', 'Not set'],
        ['After', 'Call AV.'],
      ]),
    )
    expect(described('field_changed', setting)).toEqual(
      plain('Registration enabled changed', [
        ['Before', 'No'],
        ['After', 'Yes'],
      ]),
    )
  })

  it('still says something changed when the entry names no field', () => {
    expect(described('field_changed')).toEqual(
      plain('A detail changed', [
        ['Before', 'Not set'],
        ['After', 'Not set'],
      ]),
    )
  })

  it('shows a value of a shape it does not expect as the backend wrote it', () => {
    const details = { field: 'tags', previous_value: ['a'], new_value: { b: 1 } }

    expect(described('field_changed', details).facts).toEqual([
      { label: 'Before', value: '["a"]' },
      { label: 'After', value: '{"b":1}' },
    ])
  })
})

describe('SCRUM-33 describing the review', () => {
  it.each([
    ['review_started', 'Review started'],
    ['event_completed', 'Event marked completed'],
    ['safety_review_requested', 'Sent for safety review'],
    ['event_confirmed', 'Event confirmed'],
  ])('describes %s, which has no details', (kind, title) => {
    expect(described(kind)).toEqual(plain(title))
  })

  it('gives a rejection with its reason', () => {
    const details = { outcome: 'rejected', reason: 'The hall is closed that week.' }

    expect(described('decision_recorded', details)).toEqual(
      plain('Request rejected', [['Reason', 'The hall is closed that week.']]),
    )
  })

  it('gives an approval made without a reason', () => {
    expect(described('decision_recorded', { outcome: 'approved', reason: null })).toEqual(
      plain('Request approved'),
    )
  })

  it('still says a decision was made when the entry has no outcome', () => {
    expect(described('decision_recorded')).toEqual(plain('Decision recorded'))
  })

  it("gives the coordinator's question and the organiser's answer", () => {
    expect(described('clarification_requested', { message: 'Do you need a loading bay?' })).toEqual(
      plain('Clarification requested', [['Question', 'Do you need a loading bay?']]),
    )
    expect(described('clarification_answered', { response: 'Yes, for two vans.' })).toEqual(
      plain('Clarification answered', [['Answer', 'Yes, for two vans.']]),
    )
  })
})

describe('SCRUM-33 describing the venue arrangements', () => {
  it('gives the venue and when it is asked for', () => {
    const details = {
      venue_booking_request_id: 4,
      venue_id: 12,
      starts_at: '2026-11-10T01:00:00+00:00',
      ends_at: '2026-11-10T09:00:00+00:00',
    }

    expect(described('venue_booking_requested', details)).toEqual(
      plain('Venue booking requested', [
        ['Venue ID', '12'],
        ['When', '10 Nov, 9:00 am – 5:00 pm'],
      ]),
    )
  })

  it("gives Venue Staff's approval and rejection with any reason", () => {
    const approved = { venue_id: 12, booking_id: 7, reason: null }
    const rejected = { venue_id: 15, booking_id: null, reason: 'Closed for repairs.' }

    expect(described('venue_booking_approved', approved)).toEqual(
      plain('Venue booking approved', [['Venue ID', '12']]),
    )
    expect(described('venue_booking_rejected', rejected)).toEqual(
      plain('Venue booking rejected', [
        ['Venue ID', '15'],
        ['Reason', 'Closed for repairs.'],
      ]),
    )
  })

  it('gives each field of an arrangement that changed, from and to', () => {
    const details = {
      venue_booking_request_id: 4,
      venue_id: 12,
      changes: {
        expected_occupancy: { previous: 80, new: 120 },
        required_layout: { previous: null, new: 'theatre' },
      },
    }

    expect(described('venue_arrangement_changed', details)).toEqual(
      plain('Venue arrangement changed', [
        ['Venue ID', '12'],
        ['Expected occupancy', '80 → 120'],
        ['Required layout', 'Not set → theatre'],
      ]),
    )
  })

  it('leaves out changes it cannot read', () => {
    const details = { venue_id: 12, changes: { purpose: 'not a change', layout: null } }

    expect(described('venue_arrangement_changed', details)).toEqual(
      plain('Venue arrangement changed', [['Venue ID', '12']]),
    )
  })

  it('gives the venue of a withdrawn arrangement', () => {
    expect(described('venue_arrangement_withdrawn', { venue_id: 9 })).toEqual(
      plain('Venue arrangement withdrawn', [['Venue ID', '9']]),
    )
  })
})

describe("SCRUM-84 describing Venue Staff's preparation of a booking", () => {
  it('gives the venue, the status in words and the notes', () => {
    const details = {
      venue_booking_request_id: 31,
      venue_id: 12,
      status: 'in_progress',
      notes: 'Chairs out, stage to do.',
    }

    expect(described('venue_preparation_updated', details)).toEqual(
      plain('Venue preparation updated', [
        ['Venue ID', '12'],
        ['Status', 'In progress'],
        ['Notes', 'Chairs out, stage to do.'],
      ]),
    )
  })
})

describe('SCRUM-33 describing the equipment and the safety check', () => {
  it('gives what was reserved and how many', () => {
    const details = {
      equipment_type_id: 3,
      equipment_type_name: 'Wireless microphone',
      quantity: 4,
      reservation_id: 21,
    }

    expect(described('equipment_reserved', details)).toEqual(
      plain('Equipment reserved', [
        ['Equipment', 'Wireless microphone'],
        ['Quantity', '4'],
      ]),
    )
  })

  it("gives Technical Support's outcome, how much they will provide, and why", () => {
    const details = {
      equipment_line_id: 2,
      equipment_type_id: 3,
      equipment_type_name: 'Projector',
      quantity: 4,
      provided_quantity: 2,
      status: 'partially_fulfilled',
      note: 'Two are being repaired.',
    }

    expect(described('equipment_outcome_recorded', details)).toEqual(
      plain('Equipment review recorded', [
        ['Equipment', 'Projector'],
        ['Outcome', 'Partially fulfilled'],
        ['Provided', '2 of 4'],
        ['Note', 'Two are being repaired.'],
      ]),
    )
  })

  it("gives the Safety Officer's outcome, reason and every checklist note", () => {
    const details = {
      outcome: 'changes_requested',
      checklist: SAFETY_CHECKLIST,
      reason: 'Move the stage away from the fire exit.',
    }

    expect(described('safety_outcome_recorded', details)).toEqual(
      plain('Safety check recorded', [
        ['Outcome', 'Changes requested'],
        ['Reason', 'Move the stage away from the fire exit.'],
        ['Attendance vs capacity', '80 expected in a hall for 120.'],
        ['Venue layout', 'Theatre layout, two aisles.'],
        ['Emergency access', 'Both fire exits clear.'],
        ['Accessibility', 'Ramp at the side entrance.'],
        ['Equipment placement', 'Cables taped down along the stage.'],
        ['Crowd movement', 'One-way flow at the doors.'],
        ['Venue restrictions', 'No open flames.'],
      ]),
    )
  })

  it('gives a safety approval with no reason or checklist', () => {
    expect(described('safety_outcome_recorded', { outcome: 'approved', reason: null })).toEqual(
      plain('Safety check recorded', [['Outcome', 'Approved']]),
    )
  })
})

describe("SCRUM-85 describing Technical Support's preparation of a reservation", () => {
  it('gives the equipment, the status in words and the notes', () => {
    const details = {
      reservation_id: 21,
      equipment_type_id: 3,
      equipment_type_name: 'Projector',
      status: 'ready',
      notes: 'Lamps tested.',
    }

    expect(described('equipment_preparation_updated', details)).toEqual(
      plain('Equipment preparation updated', [
        ['Equipment', 'Projector'],
        ['Status', 'Ready'],
        ['Notes', 'Lamps tested.'],
      ]),
    )
  })
})

describe('SCRUM-33 an entry missing some of its details', () => {
  it.each<[string, Record<string, unknown>, string[]]>([
    [
      'venue_booking_requested',
      { venue_id: 12, starts_at: '2026-11-10T01:00:00+00:00' },
      ['Venue ID'],
    ],
    ['venue_arrangement_changed', { venue_id: 12 }, ['Venue ID']],
    ['venue_booking_approved', { venue_id: null, reason: 'Closed.' }, ['Reason']],
    ['equipment_outcome_recorded', { status: 'unavailable', quantity: 4 }, ['Outcome']],
    ['equipment_outcome_recorded', { equipment_type_name: 'Projector' }, ['Equipment']],
    ['equipment_preparation_updated', { status: 'done', notes: 'Lamps tested.' }, ['Notes']],
    ['safety_outcome_recorded', { reason: 'Too crowded.' }, ['Reason']],
    ['venue_preparation_updated', { venue_id: 12, status: 'done', notes: null }, ['Venue ID']],
  ])('leaves out of %s the facts it cannot make', (kind, details, labels) => {
    expect(described(kind, details).facts.map((fact) => fact.label)).toEqual(labels)
  })
})

describe('SCRUM-33 a kind added to the backend since', () => {
  it('says what happened in words made from its name, and nothing more', () => {
    const details = { venue_id: 12, expired_at: '2026-11-20T01:00:00+00:00' }

    expect(described('venue_hold_expired', details)).toEqual(plain('Venue hold expired'))
  })

  it('is not mistaken for a kind it shares a name with in JavaScript', () => {
    expect(described('constructor')).toEqual(plain('Constructor'))
  })
})
