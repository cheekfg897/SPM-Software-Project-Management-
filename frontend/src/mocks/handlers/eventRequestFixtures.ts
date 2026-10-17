import type { EventRecord, EventRequest } from '@/features/eventRequests/api'

import { MOCK_ACCOUNTS } from '../fixtures/accounts'

/** A coordinator as the mock stores one. The record shows the name and email, never the id. */
export interface MockCoordinator {
  id: number
  full_name: string
  email: string
}

/** What an event's record shows besides the request and its coordinator (ADR-0056). */
export type MockRecordSections = Pick<
  EventRecord,
  'programme_notes' | 'decision' | 'clarifications'
>

/** A request as the mock stores it: what the backend shows, and who wrote it for whom. */
export interface MockEventRequest {
  /** Never shown: the backend keeps who wrote a request and for which organisation. */
  organiserId: number
  organisationId: number
  /** Null until the Lead assigns one (ADR-0036). */
  coordinator: MockCoordinator | null
  request: EventRequest
  record: MockRecordSections
  /** The event has an equipment request, so its decision can't change (SCRUM-31 AC7). */
  hasEquipmentRequest?: true
}

/** A record with nothing on it yet beyond the request: no note, decision or question. */
export const NOTHING_RECORDED: MockRecordSections = {
  programme_notes: null,
  decision: null,
  clarifications: [],
}

/** Someone in the mock organiser's organisation who isn't a mock account. */
const COLLEAGUE_ID = 7
const ORGANISER = MOCK_ACCOUNTS.organiser
/** Another organisation's organiser: an id no mock account has. */
const OTHER_ORGANISER_ID = 90
const OTHER_ORGANISATION_ID = 2

/** The mock coordinator, who can log in. */
const CHLOE: MockCoordinator = {
  id: MOCK_ACCOUNTS.coordinator.id,
  full_name: MOCK_ACCOUNTS.coordinator.full_name,
  email: MOCK_ACCOUNTS.coordinator.email,
}
/** Another coordinator, who isn't a mock account: their events are never Chloe's. */
const MARCUS: MockCoordinator = {
  id: 99,
  full_name: 'Marcus Tan',
  email: 'marcus@connectsphere.test',
}

/** A coordinator who can log in, whose events are all another organisation's (ADR-0060). */
const PRIYA: MockCoordinator = {
  id: MOCK_ACCOUNTS.reviewingCoordinator.id,
  full_name: MOCK_ACCOUNTS.reviewingCoordinator.full_name,
  email: MOCK_ACCOUNTS.reviewingCoordinator.email,
}
/** The organiser of another organisation who can log in, and wrote Priya's events. */
const SARA = MOCK_ACCOUNTS.otherOrganiser

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
 *
 * Chloe, the mock coordinator, has two of the organiser's requests and three of another
 * organisation's, which the booking and equipment mocks also hold, so her links lead somewhere.
 * Marcus has two of the organiser's, one dated between hers, so a list that leaks it shows it.
 * Priya has four of organisation 2's (submitted, under review, approved and rejected), so
 * reviewing and deciding them changes nothing the organiser's or Chloe's lists show (ADR-0060).
 * Sara wrote all but the one under review, which her colleague did, so answering its question
 * shows any organiser of the organisation may. The one under
 * review and the approved one have an equipment request, so the approved one's decision is
 * locked; a first decision never is (ADR-0028).
 */
export const MOCK_EVENT_REQUESTS: readonly MockEventRequest[] = [
  {
    organiserId: OTHER_ORGANISER_ID,
    organisationId: OTHER_ORGANISATION_ID,
    coordinator: null,
    record: NOTHING_RECORDED,
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
    coordinator: null,
    record: NOTHING_RECORDED,
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
    coordinator: CHLOE,
    record: {
      ...NOTHING_RECORDED,
      programme_notes: 'Keynote at 9:30, breakout rooms after lunch.',
    },
    request: {
      ...DETAILS,
      reference: 'EVR-7K2M9QXA',
      status: 'under_review',
      name: 'Partner Summit',
      purpose: 'Meet our channel partners and plan next year together.',
      venue_requirements: 'A main hall for 250 and four breakout rooms.',
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
    coordinator: null,
    record: NOTHING_RECORDED,
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
    coordinator: null,
    record: NOTHING_RECORDED,
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
    coordinator: MARCUS,
    record: {
      ...NOTHING_RECORDED,
      decision: {
        outcome: 'approved',
        reason: null,
        decided_by: 'Marcus Tan',
        decided_at: '2026-09-30T11:00:00+08:00',
      },
    },
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
    coordinator: CHLOE,
    record: {
      ...NOTHING_RECORDED,
      clarifications: [
        {
          message: 'Will the roadshow need a loading bay for the demo vehicles?',
          requested_by: 'Chloe Lim',
          requested_at: '2026-09-26T10:00:00+08:00',
          response: 'Yes, for two vans between 11am and noon.',
          answered_by: 'Omar Rahman',
          answered_at: '2026-09-26T14:30:00+08:00',
        },
        {
          message: 'Can the start move to 2pm so the vans can unload first?',
          requested_by: 'Chloe Lim',
          requested_at: '2026-09-27T09:15:00+08:00',
          response: null,
          answered_by: null,
          answered_at: null,
        },
      ],
    },
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
    coordinator: MARCUS,
    record: {
      ...NOTHING_RECORDED,
      decision: {
        outcome: 'rejected',
        reason: 'The proposed date clashes with the venue refurbishment.',
        decided_by: 'Marcus Tan',
        decided_at: '2026-09-29T15:20:00+08:00',
      },
    },
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
  {
    organiserId: OTHER_ORGANISER_ID,
    organisationId: OTHER_ORGANISATION_ID,
    coordinator: CHLOE,
    record: NOTHING_RECORDED,
    request: {
      ...DETAILS,
      reference: 'EVR-BOOK0101',
      status: 'approved',
      name: 'Harbourfront Careers Fair',
      proposed_date: '2026-11-10',
      end_date: '2026-11-10',
      start_time: '09:00:00',
      end_time: '17:00:00',
      expected_attendance: 80,
      accessibility_needs: 'Step-free access',
      registration_required: true,
      created_at: '2026-10-04T03:00:00+00:00',
    },
  },
  {
    organiserId: OTHER_ORGANISER_ID,
    organisationId: OTHER_ORGANISATION_ID,
    coordinator: CHLOE,
    record: NOTHING_RECORDED,
    request: {
      ...DETAILS,
      reference: 'EVR-MOCK0001',
      status: 'approved',
      name: 'Evening Product Showcase',
      proposed_date: '2026-10-12',
      end_date: '2026-10-12',
      start_time: '19:30:00',
      end_time: '22:00:00',
      expected_attendance: 60,
      created_at: '2026-10-01T03:00:00+00:00',
    },
  },
  {
    organiserId: OTHER_ORGANISER_ID,
    organisationId: OTHER_ORGANISATION_ID,
    coordinator: CHLOE,
    record: NOTHING_RECORDED,
    request: {
      ...DETAILS,
      reference: 'EVR-BOOK0102',
      status: 'confirmed',
      name: 'Year-End Town Hall',
      proposed_date: '2026-11-10',
      end_date: '2026-11-10',
      start_time: '09:00:00',
      end_time: '17:00:00',
      expected_attendance: 80,
      accessibility_needs: 'Step-free access',
      created_at: '2026-09-27T03:00:00+00:00',
    },
  },
  {
    organiserId: SARA.id,
    organisationId: SARA.organisation_id,
    coordinator: PRIYA,
    record: NOTHING_RECORDED,
    request: {
      ...DETAILS,
      reference: 'EVR-RV4K8N2P',
      status: 'submitted',
      name: 'Community Hackathon',
      purpose: 'Two days of building tools for local charities.',
      proposed_date: '2026-11-26',
      end_date: '2026-11-26',
      start_time: '10:00:00',
      end_time: '18:00:00',
      expected_attendance: 150,
      created_at: '2026-10-02T03:00:00+00:00',
    },
  },
  {
    organiserId: OTHER_ORGANISER_ID,
    organisationId: SARA.organisation_id,
    coordinator: PRIYA,
    hasEquipmentRequest: true,
    record: NOTHING_RECORDED,
    request: {
      ...DETAILS,
      reference: 'EVR-RV2D5F8J',
      status: 'under_review',
      name: 'Design Sprint Showcase',
      proposed_date: '2026-11-18',
      end_date: '2026-11-18',
      start_time: '14:00:00',
      end_time: '17:00:00',
      expected_attendance: 70,
      created_at: '2026-09-30T03:00:00+00:00',
    },
  },
  {
    organiserId: SARA.id,
    organisationId: SARA.organisation_id,
    coordinator: PRIYA,
    hasEquipmentRequest: true,
    record: {
      ...NOTHING_RECORDED,
      decision: {
        outcome: 'approved',
        reason: null,
        decided_by: 'Priya Nair',
        decided_at: '2026-09-28T16:00:00+08:00',
      },
    },
    request: {
      ...DETAILS,
      reference: 'EVR-RV7T3M5Q',
      status: 'approved',
      name: 'Sustainability Forum',
      proposed_date: '2026-12-08',
      end_date: '2026-12-08',
      start_time: '09:30:00',
      end_time: '13:00:00',
      expected_attendance: 90,
      created_at: '2026-09-24T03:00:00+00:00',
    },
  },
  {
    organiserId: SARA.id,
    organisationId: SARA.organisation_id,
    coordinator: PRIYA,
    record: {
      ...NOTHING_RECORDED,
      decision: {
        outcome: 'rejected',
        reason: 'The atrium is closed for the national holiday.',
        decided_by: 'Priya Nair',
        decided_at: '2026-09-23T10:45:00+08:00',
      },
    },
    request: {
      ...DETAILS,
      reference: 'EVR-RV9H6C1W',
      status: 'rejected',
      name: 'Alumni Mixer',
      proposed_date: '2026-11-03',
      end_date: '2026-11-03',
      start_time: '18:00:00',
      end_time: '21:00:00',
      expected_attendance: 110,
      created_at: '2026-09-22T03:00:00+00:00',
    },
  },
]
