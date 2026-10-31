import type { EventRequest } from '@/features/eventRequests/api'

import { filtersFromEvent } from './eventFilters'

/** A one-day event as the coordinator's record sends it, with every requirement written down. */
const EVENT: EventRequest = {
  reference: 'EVR-7K2M9QXA',
  status: 'approved',
  name: 'Partner Summit',
  purpose: null,
  description: null,
  proposed_date: '2026-11-12',
  end_date: '2026-11-12',
  start_time: '09:00:00',
  end_time: '17:30:00',
  expected_attendance: 250,
  venue_requirements: 'A main hall in theatre style, with a projector.',
  accessibility_needs: 'Step-free access to the hall.',
  equipment_requirements: null,
  registration_required: false,
  created_at: '2026-10-06T02:00:00+00:00',
}

describe('SCRUM-90 venue search filters filled in from an event', () => {
  it('takes the period from its date and times, and the minimum capacity from its attendance (AC2)', () => {
    expect(filtersFromEvent(EVENT)).toMatchObject({
      date: '2026-11-12',
      start: '09:00',
      end: '17:30',
      end_date: '',
      min_capacity: '250',
    })
  })

  it('takes the end date of an event that ends on a later day (AC2)', () => {
    const overnight = { ...EVENT, end_date: '2026-11-13', end_time: '01:00:00' }

    expect(filtersFromEvent(overnight)).toMatchObject({ end_date: '2026-11-13', end: '01:00' })
  })

  it('leaves layout, facilities, accessibility and location empty, whatever the event wrote (AC3)', () => {
    expect(filtersFromEvent(EVENT)).toMatchObject({
      location: '',
      required_layout: '',
      required_facilities: [],
      required_accessibility: [],
    })
  })

  it('leaves a detail the event has not recorded empty rather than guessing it', () => {
    const unrecorded = {
      ...EVENT,
      proposed_date: null,
      end_date: null,
      start_time: null,
      end_time: null,
      expected_attendance: null,
    }

    expect(filtersFromEvent(unrecorded)).toMatchObject({
      date: '',
      start: '',
      end: '',
      end_date: '',
      min_capacity: '',
    })
  })
})
