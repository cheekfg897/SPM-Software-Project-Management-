import { MOCK_ACCOUNTS } from '../fixtures/accounts'

import { NOTHING_RECORDED } from './eventRequestFixtures'
import type { MockCoordinator, MockEventRequest } from './eventRequestFixtures'

/** A venue arrangement's status, as the venue module names it (BookingRequestStatus). */
export type MockArrangementStatus =
  'pending' | 'withdrawn' | 'approved' | 'rejected' | 'conflicting'

/** One of the event's venue arrangements: all the gates read is its id and status. */
export interface MockArrangement {
  id: number
  status: MockArrangementStatus
}

/**
 * What the backend counts when the coordinator plans an event, which the other feature mocks
 * keep in their own copies of events (ADR-0075): its venue arrangements, in period order, the
 * ids of its equipment requests Technical Support hasn't answered, whether the Safety Officer
 * has approved it (`has_safety_approval`), its registration settings as the backend stores them
 * (ADR-0043) and how many attendees have registered.
 */
export interface MockPlanning {
  arrangements: readonly MockArrangement[]
  equipmentWithoutOutcome: readonly number[]
  isSafetyApproved: boolean
  registration_enabled: boolean
  registration_capacity: number | null
  registeredCount: number
}

/**
 * An event the mock holds nothing for: no venue arranged, no equipment requested, no safety
 * approval, registration closed with no capacity and nobody registered.
 */
export const NOTHING_PLANNED: MockPlanning = {
  arrangements: [],
  equipmentWithoutOutcome: [],
  isSafetyApproved: false,
  registration_enabled: false,
  registration_capacity: null,
  registeredCount: 0,
}

/** Hana, the mock coordinator whose events are past their first decision (ADR-0075). */
const HANA: MockCoordinator = {
  id: MOCK_ACCOUNTS.planningCoordinator.id,
  full_name: MOCK_ACCOUNTS.planningCoordinator.full_name,
  email: MOCK_ACCOUNTS.planningCoordinator.email,
}
/** Another organisation's organiser, not a mock account, so no organiser's list changes. */
const ORGANISER_ID = 90
const ORGANISATION_ID = 2

/** What every one of Hana's events shares unless it says otherwise. */
const HANAS_EVENT = {
  organiserId: ORGANISER_ID,
  organisationId: ORGANISATION_ID,
  coordinator: HANA,
  record: NOTHING_RECORDED,
}

/** The details every one of Hana's events shares unless it says otherwise. */
const DETAILS = {
  purpose: null,
  description: null,
  venue_requirements: null,
  accessibility_needs: null,
  equipment_requirements: null,
  registration_required: false,
  expected_attendance: 150,
  start_time: '10:00:00',
  end_time: '16:00:00',
}

/**
 * Hana's events. Approved: EVR-PLAN0001 still has a pending venue arrangement (42) beside an
 * approved one and a withdrawn one, and an unanswered equipment request (43), so the Safety
 * Review gate names both, and its decision can no longer change (SCRUM-31 AC7); EVR-PLAN0002 is settled, its only other arrangement withdrawn.
 * In Safety Review: EVR-PLAN0003 has the Safety Officer's approval and is settled;
 * EVR-PLAN0004 has no approval, a rejected arrangement (48) beside an approved one and an
 * unanswered equipment request (49), so confirming it names a gap in each area.
 * Confirmed, against the mock's "now" (MOCK_NOW, 5 Oct 12:00 pm): EVR-PLAN0005 ends exactly
 * then, so it has ended; EVR-PLAN0006 began the day before and ends a minute later, so it hasn't.
 * EVR-PLAN0005's registration is open for 50 with 30 registered, though its organiser didn't ask
 * for it; EVR-PLAN0006's organiser did, and nothing is set yet.
 */
export const PLANNING_EVENT_REQUESTS: readonly MockEventRequest[] = [
  {
    ...HANAS_EVENT,
    planning: {
      ...NOTHING_PLANNED,
      arrangements: [
        { id: 41, status: 'approved' },
        { id: 40, status: 'withdrawn' },
        { id: 42, status: 'pending' },
      ],
      equipmentWithoutOutcome: [43],
    },
    hasEquipmentRequest: true,
    request: {
      ...DETAILS,
      reference: 'EVR-PLAN0001',
      status: 'approved',
      name: 'Riverside Food Festival',
      proposed_date: '2026-11-21',
      end_date: '2026-11-21',
      created_at: '2026-09-21T03:00:00+00:00',
    },
  },
  {
    ...HANAS_EVENT,
    planning: {
      ...NOTHING_PLANNED,
      arrangements: [
        { id: 44, status: 'withdrawn' },
        { id: 45, status: 'approved' },
      ],
      equipmentWithoutOutcome: [],
    },
    request: {
      ...DETAILS,
      reference: 'EVR-PLAN0002',
      status: 'approved',
      name: 'Founders Breakfast',
      proposed_date: '2026-11-14',
      end_date: '2026-11-14',
      created_at: '2026-09-20T03:00:00+00:00',
    },
  },
  {
    ...HANAS_EVENT,
    planning: {
      ...NOTHING_PLANNED,
      arrangements: [{ id: 46, status: 'approved' }],
      isSafetyApproved: true,
    },
    request: {
      ...DETAILS,
      reference: 'EVR-PLAN0003',
      status: 'safety_review',
      name: 'Harbour Lights Concert',
      proposed_date: '2026-11-28',
      end_date: '2026-11-28',
      created_at: '2026-09-19T03:00:00+00:00',
    },
  },
  {
    ...HANAS_EVENT,
    planning: {
      ...NOTHING_PLANNED,
      arrangements: [
        { id: 47, status: 'approved' },
        { id: 48, status: 'rejected' },
      ],
      equipmentWithoutOutcome: [49],
    },
    hasEquipmentRequest: true,
    request: {
      ...DETAILS,
      reference: 'EVR-PLAN0004',
      status: 'safety_review',
      name: 'Winter Charity Run',
      proposed_date: '2026-12-06',
      end_date: '2026-12-06',
      created_at: '2026-09-18T03:00:00+00:00',
    },
  },
  {
    ...HANAS_EVENT,
    planning: {
      ...NOTHING_PLANNED,
      registration_enabled: true,
      registration_capacity: 50,
      registeredCount: 30,
    },
    request: {
      ...DETAILS,
      reference: 'EVR-PLAN0005',
      status: 'confirmed',
      name: 'Autumn Book Fair',
      proposed_date: '2026-10-05',
      end_date: '2026-10-05',
      end_time: '12:00:00',
      created_at: '2026-09-17T03:00:00+00:00',
    },
  },
  {
    ...HANAS_EVENT,
    request: {
      ...DETAILS,
      reference: 'EVR-PLAN0006',
      status: 'confirmed',
      name: 'Weekend Coding Camp',
      registration_required: true,
      proposed_date: '2026-10-04',
      end_date: '2026-10-05',
      end_time: '12:01:00',
      created_at: '2026-09-16T03:00:00+00:00',
    },
  },
]
