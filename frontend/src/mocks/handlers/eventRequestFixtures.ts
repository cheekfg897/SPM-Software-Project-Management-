import type { EventRequest } from '@/features/eventRequests/api'

import { MOCK_ACCOUNTS } from '../fixtures/accounts'

/** A request as the mock stores it: what the backend shows, and who wrote it for whom. */
export interface MockEventRequest {
  /** Never shown: the backend keeps who wrote a request and for which organisation. */
  organiserId: number
  organisationId: number
  request: EventRequest
}

/** Someone in the mock organiser's organisation who isn't a mock account. */
const COLLEAGUE_ID = 7
const ORGANISER = MOCK_ACCOUNTS.organiser

/** The details every request shares unless it says otherwise. */
const DETAILS = {
  purpose: null,
  description: null,
  venue_requirements: null,
  accessibility_needs: null,
  equipment_requirements: null,
  registration_required: false,
}

/**
 * The event requests every mock run starts with. The newest two are a colleague's draft and
 * another organisation's request, so a mock or page that leaks either shows it first. Event
 * dates don't follow the newest-first order, so anything that re-sorts them shows too.
 */
export const MOCK_EVENT_REQUESTS: readonly MockEventRequest[] = [
  {
    organiserId: 9,
    organisationId: 2,
    request: {
      ...DETAILS,
      reference: 'EVR-N5QS3V9C',
      status: 'submitted',
      name: 'Another Organisation Conference',
      proposed_date: '2026-11-20',
      end_date: '2026-11-20',
      start_time: '09:00:00',
      end_time: '18:00:00',
      expected_attendance: 400,
      created_at: '2026-10-08T01:00:00+00:00',
    },
  },
  {
    organiserId: COLLEAGUE_ID,
    organisationId: ORGANISER.organisation_id,
    request: {
      ...DETAILS,
      reference: 'EVR-H2PL8R6K',
      status: 'draft',
      name: "A colleague's draft",
      proposed_date: null,
      end_date: null,
      start_time: null,
      end_time: null,
      expected_attendance: null,
      created_at: '2026-10-07T01:00:00+00:00',
    },
  },
  {
    organiserId: ORGANISER.id,
    organisationId: ORGANISER.organisation_id,
    request: {
      ...DETAILS,
      reference: 'EVR-7K2M9QXA',
      status: 'under_review',
      name: 'Partner Summit',
      proposed_date: '2026-11-12',
      end_date: '2026-11-12',
      start_time: '09:00:00',
      end_time: '17:00:00',
      expected_attendance: 250,
      created_at: '2026-10-06T02:00:00+00:00',
    },
  },
  {
    organiserId: ORGANISER.id,
    organisationId: ORGANISER.organisation_id,
    request: {
      ...DETAILS,
      reference: 'EVR-3HD8PL2W',
      status: 'draft',
      name: 'Volunteer Thank-You Dinner',
      proposed_date: null,
      end_date: null,
      start_time: null,
      end_time: null,
      expected_attendance: null,
      created_at: '2026-10-05T03:00:00+00:00',
    },
  },
  {
    organiserId: COLLEAGUE_ID,
    organisationId: ORGANISER.organisation_id,
    request: {
      ...DETAILS,
      reference: 'EVR-Q4ZT6N1B',
      status: 'submitted',
      name: 'Product Launch Night',
      proposed_date: '2026-10-30',
      end_date: '2026-10-30',
      start_time: '19:00:00',
      end_time: '22:00:00',
      expected_attendance: 120,
      created_at: '2026-10-03T04:00:00+00:00',
    },
  },
  {
    organiserId: ORGANISER.id,
    organisationId: ORGANISER.organisation_id,
    request: {
      ...DETAILS,
      reference: 'EVR-W9CR5E7M',
      status: 'approved',
      name: 'Leadership Offsite',
      proposed_date: '2026-12-03',
      end_date: '2026-12-04',
      start_time: '10:00:00',
      end_time: '16:00:00',
      expected_attendance: 40,
      created_at: '2026-09-28T05:00:00+00:00',
    },
  },
  {
    organiserId: ORGANISER.id,
    organisationId: ORGANISER.organisation_id,
    request: {
      ...DETAILS,
      reference: 'EVR-B6YF2K8V',
      status: 'awaiting_clarification',
      name: 'Customer Roadshow',
      proposed_date: '2026-11-05',
      end_date: '2026-11-05',
      start_time: '13:00:00',
      end_time: '17:30:00',
      expected_attendance: 80,
      created_at: '2026-09-25T06:00:00+00:00',
    },
  },
  {
    organiserId: ORGANISER.id,
    organisationId: ORGANISER.organisation_id,
    request: {
      ...DETAILS,
      reference: 'EVR-M1XJ7T3D',
      status: 'rejected',
      name: 'Annual Gala',
      proposed_date: '2026-10-24',
      end_date: '2026-10-24',
      start_time: '18:30:00',
      end_time: '23:00:00',
      expected_attendance: 600,
      created_at: '2026-09-20T07:00:00+00:00',
    },
  },
]
