import type { SafetyCheckOutcome } from '@/features/eventRequests/api'
import type { AwaitingSafetyReview } from '@/features/safety/api'

/**
 * Events for the Safety Officer's mock (SCRUM-97, SCRUM-98). Listed out of date order, so the
 * mock's sort is what puts them soonest first. e2e/safety.spec.ts names two of them.
 */

export interface MockSafetyEvent extends AwaitingSafetyReview {
  /** The Safety Officer has approved the current check: still in Safety Review, not listed. */
  safety_approved: boolean
  /** What the Safety Officer recorded on the current check, for the staff record (ADR-0095). */
  outcome: SafetyCheckOutcome | null
}

/** A note on each checklist item, as the Safety Officer recorded them on the seeded checks. */
const SEEDED_CHECKLIST = {
  attendance_vs_capacity: 'Within capacity.',
  venue_layout: 'Layout agreed with Venue Staff.',
  emergency_access: 'Exits kept clear.',
  accessibility: 'Step-free entrance.',
  equipment_placement: 'Cables taped down.',
  crowd_movement: 'One-way flow at the doors.',
  venue_restrictions: 'No open flames.',
}

/** On the list: a gala with two venues' worth of detail and equipment with outcomes. */
export const MOCK_GALA: MockSafetyEvent = {
  event: {
    reference: 'EVR-SAFE0002',
    name: 'Harbour Lights Gala',
    proposed_date: '2026-12-04',
    end_date: '2026-12-04',
    start_time: '18:00:00',
    end_time: '23:00:00',
    status: 'safety_review',
    expected_attendance: 400,
    accessibility_needs: 'Wheelchair seating for six guests',
  },
  venues: [
    {
      id: 9201,
      name: 'Marina Ballroom',
      capacity: 500,
      layouts: ['banquet', 'theatre'],
      facilities: ['stage', 'pa system'],
      accessibility_features: ['wheelchair access', 'hearing loop'],
      starts_at: '2026-12-04T17:00:00+08:00',
      ends_at: '2026-12-04T23:30:00+08:00',
    },
  ],
  equipment: [
    {
      id: 9301,
      equipment_type_name: 'Projector',
      quantity: 2,
      notes: 'Ceiling mount',
      status: 'fulfilled',
      provided_quantity: 2,
      outcome_note: null,
    },
    {
      id: 9302,
      equipment_type_name: 'Wireless microphone',
      quantity: 6,
      notes: null,
      status: 'partially_fulfilled',
      provided_quantity: 4,
      outcome_note: 'Only four in stock that week.',
    },
  ],
  safety_approved: false,
  outcome: null,
}

/** On the list, soonest: a fair with no equipment and a venue with few details. */
export const MOCK_FAIR: MockSafetyEvent = {
  event: {
    reference: 'EVR-SAFE0001',
    name: 'Community Health Fair',
    proposed_date: '2026-11-21',
    end_date: null,
    start_time: '09:00:00',
    end_time: '16:00:00',
    status: 'safety_review',
    expected_attendance: 250,
    accessibility_needs: null,
  },
  venues: [
    {
      id: 9202,
      name: 'Atrium Hall',
      capacity: 300,
      layouts: ['exhibition'],
      facilities: [],
      accessibility_features: [],
      starts_at: '2026-11-21T08:00:00+08:00',
      ends_at: '2026-11-21T17:00:00+08:00',
    },
  ],
  equipment: [],
  safety_approved: false,
  outcome: null,
}

/** On the list between the other two: the gala's day but earlier, so the time decides. */
export const MOCK_TOWN_HALL: MockSafetyEvent = {
  event: {
    reference: 'EVR-SAFE0003',
    name: 'Year-End Town Hall',
    proposed_date: '2026-12-04',
    end_date: '2026-12-04',
    start_time: '10:00:00',
    end_time: '12:00:00',
    status: 'safety_review',
    expected_attendance: 120,
    accessibility_needs: 'Live captions',
  },
  venues: [
    {
      id: 9203,
      name: 'Riverside Auditorium',
      capacity: 150,
      layouts: ['theatre'],
      facilities: ['projector screen'],
      accessibility_features: ['step-free entrance'],
      starts_at: '2026-12-04T09:00:00+08:00',
      ends_at: '2026-12-04T12:30:00+08:00',
    },
  ],
  equipment: [
    {
      id: 9303,
      equipment_type_name: 'Lectern',
      quantity: 1,
      notes: null,
      status: 'unavailable',
      provided_quantity: 0,
      outcome_note: 'Being repaired.',
    },
  ],
  safety_approved: false,
  outcome: null,
}

/** Already approved by the Safety Officer: in Safety Review, but never listed. */
export const MOCK_APPROVED_LAUNCH: MockSafetyEvent = {
  event: {
    reference: 'EVR-SAFE0004',
    name: 'Product Launch Evening',
    proposed_date: '2026-11-01',
    end_date: null,
    start_time: '18:00:00',
    end_time: '21:00:00',
    status: 'safety_review',
    expected_attendance: 90,
    accessibility_needs: null,
  },
  venues: [],
  equipment: [],
  safety_approved: true,
  outcome: {
    outcome: 'approved',
    checklist: SEEDED_CHECKLIST,
    reason: null,
    recorded_by: 'Sana Iyer',
    recorded_at: '2026-10-02T15:00:00+08:00',
    flagged_arrangement_count: 0,
    reopened_line_count: 0,
  },
}

/** Sent back to planning by an earlier check: Approved, so an outcome is refused. */
export const MOCK_RETURNED_SUMMIT: MockSafetyEvent = {
  event: {
    reference: 'EVR-SAFE0005',
    name: 'Partner Summit',
    proposed_date: '2026-11-10',
    end_date: null,
    start_time: '09:00:00',
    end_time: '17:00:00',
    status: 'approved',
    expected_attendance: 200,
    accessibility_needs: null,
  },
  venues: [],
  equipment: [],
  safety_approved: false,
  outcome: {
    outcome: 'changes_requested',
    checklist: SEEDED_CHECKLIST,
    reason: 'Add a second fire exit to the plan.',
    recorded_by: 'Sana Iyer',
    recorded_at: '2026-10-01T11:00:00+08:00',
    flagged_arrangement_count: 0,
    reopened_line_count: 0,
  },
}

/** Every event the mock starts with, neither in date order nor in time order. */
export const MOCK_SAFETY_EVENTS: readonly MockSafetyEvent[] = [
  MOCK_GALA,
  MOCK_FAIR,
  MOCK_TOWN_HALL,
  MOCK_APPROVED_LAUNCH,
  MOCK_RETURNED_SUMMIT,
]
