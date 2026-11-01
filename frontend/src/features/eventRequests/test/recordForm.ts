import type { EventRecord } from '../api'

/**
 * An event's record and the edit form as it opens on it, for the tests of what the coordinator's
 * edit (SCRUM-33) and the organiser's change request (SCRUM-56) send.
 */

export const RECORD: EventRecord = {
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
  equipment_lines: [],
  change_requests: [],
}

/** The form as it opens on RECORD, with `typed` changed. */
export function formWith(typed: Record<string, string> = {}): FormData {
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
