import type { EventHistoryEntry, Registrant } from '@/features/eventRequests/api'

/**
 * What the mock's events have on record besides the request (eventRequestFixtures.ts), by
 * reference: their history (SCRUM-33) and who registered (SCRUM-55). An event with no entry
 * here has none of either yet, and no capacity.
 *
 * Each history is written as staff see it, oldest first; the mock leaves out of an organiser's
 * copy what the backend does. Partner Summit and Leadership Offsite are the mock organiser's,
 * so each holds entries an organiser must not see (an internal planning note; equipment and the
 * safety check), next to ones they must. The Year-End Town Hall, Chloe's confirmed event, has
 * been through every step to confirmation, and three people registered for its 80 places.
 */

const LEON = 'Leon Goh'
const CHLOE = 'Chloe Lim'
const MARCUS = 'Marcus Tan'
const TARIQ = 'Tariq Hassan'
const SANA = 'Sana Iyer'
const VERA = 'Vera Goh'

/** The Safety Officer's notes on the seven checklist items (SCRUM-98 AC2). */
const SAFETY_CHECKLIST = {
  attendance_vs_capacity: '80 expected in a hall for 120.',
  venue_layout: 'Theatre layout with two aisles.',
  emergency_access: 'Both fire exits are clear.',
  accessibility: 'Ramp at the side entrance.',
  equipment_placement: 'Cables taped down along the stage.',
  crowd_movement: 'One-way flow at the doors.',
  venue_restrictions: 'No open flames.',
}

export const MOCK_EVENT_HISTORY: Readonly<Record<string, readonly EventHistoryEntry[]>> = {
  'EVR-7K2M9QXA': [
    {
      kind: 'coordinator_assigned',
      occurred_at: '2026-10-06T14:00:00+08:00',
      actor_name: LEON,
      details: { coordinator_name: CHLOE },
    },
    {
      kind: 'review_started',
      occurred_at: '2026-10-07T09:30:00+08:00',
      actor_name: CHLOE,
      details: {},
    },
    {
      kind: 'field_changed',
      occurred_at: '2026-10-07T11:00:00+08:00',
      actor_name: CHLOE,
      details: {
        field: 'internal_planning_notes',
        previous_value: null,
        new_value: 'Ask facilities whether the east wing is free.',
        significant: false,
      },
    },
    {
      kind: 'field_changed',
      occurred_at: '2026-10-08T10:15:00+08:00',
      actor_name: CHLOE,
      details: {
        field: 'expected_attendance',
        previous_value: 200,
        new_value: 250,
        significant: true,
      },
    },
  ],
  'EVR-W9CR5E7M': [
    {
      // Assigned before the Lead existed, so by the system: no one's name (ADR-0018).
      kind: 'coordinator_assigned',
      occurred_at: '2026-09-28T15:00:00+08:00',
      actor_name: null,
      details: { coordinator_name: MARCUS },
    },
    {
      kind: 'decision_recorded',
      occurred_at: '2026-09-30T11:00:00+08:00',
      actor_name: MARCUS,
      details: { outcome: 'approved', reason: null },
    },
    {
      kind: 'equipment_reserved',
      occurred_at: '2026-10-02T10:00:00+08:00',
      actor_name: TARIQ,
      details: {
        equipment_type_id: 2,
        equipment_type_name: 'Wireless microphone',
        quantity: 4,
        reservation_id: 3,
      },
    },
    {
      kind: 'equipment_outcome_recorded',
      occurred_at: '2026-10-02T10:05:00+08:00',
      actor_name: TARIQ,
      details: {
        equipment_line_id: 6,
        equipment_type_id: 2,
        equipment_type_name: 'Wireless microphone',
        quantity: 4,
        provided_quantity: 4,
        status: 'fulfilled',
        note: null,
      },
    },
    {
      kind: 'safety_review_requested',
      occurred_at: '2026-10-05T09:00:00+08:00',
      actor_name: MARCUS,
      details: {},
    },
    {
      kind: 'safety_outcome_recorded',
      occurred_at: '2026-10-06T16:00:00+08:00',
      actor_name: SANA,
      details: {
        outcome: 'changes_requested',
        checklist: SAFETY_CHECKLIST,
        reason: 'Keep the terrace exit clear during the dinner.',
      },
    },
  ],
  'EVR-BOOK0102': [
    {
      kind: 'coordinator_assigned',
      occurred_at: '2026-09-27T14:00:00+08:00',
      actor_name: LEON,
      details: { coordinator_name: CHLOE },
    },
    {
      kind: 'review_started',
      occurred_at: '2026-09-28T09:00:00+08:00',
      actor_name: CHLOE,
      details: {},
    },
    {
      kind: 'decision_recorded',
      occurred_at: '2026-09-28T16:30:00+08:00',
      actor_name: CHLOE,
      details: { outcome: 'approved', reason: null },
    },
    {
      kind: 'venue_booking_requested',
      occurred_at: '2026-09-29T10:00:00+08:00',
      actor_name: CHLOE,
      details: {
        venue_booking_request_id: 2,
        venue_id: 1,
        starts_at: '2026-11-10T01:00:00+00:00',
        ends_at: '2026-11-10T09:00:00+00:00',
      },
    },
    {
      kind: 'venue_booking_approved',
      occurred_at: '2026-09-30T11:00:00+08:00',
      actor_name: VERA,
      details: { venue_booking_request_id: 2, venue_id: 1, booking_id: 5, reason: null },
    },
    {
      kind: 'equipment_outcome_recorded',
      occurred_at: '2026-10-01T15:00:00+08:00',
      actor_name: TARIQ,
      details: {
        equipment_line_id: 4,
        equipment_type_id: 1,
        equipment_type_name: 'Projector',
        quantity: 2,
        provided_quantity: 1,
        status: 'partially_fulfilled',
        note: 'One projector is out for repair.',
      },
    },
    {
      kind: 'safety_review_requested',
      occurred_at: '2026-10-03T09:00:00+08:00',
      actor_name: CHLOE,
      details: {},
    },
    {
      kind: 'safety_outcome_recorded',
      occurred_at: '2026-10-04T14:00:00+08:00',
      actor_name: SANA,
      details: { outcome: 'approved', checklist: SAFETY_CHECKLIST, reason: null },
    },
    {
      kind: 'event_confirmed',
      occurred_at: '2026-10-05T10:00:00+08:00',
      actor_name: CHLOE,
      details: {},
    },
    {
      kind: 'field_changed',
      occurred_at: '2026-10-05T10:30:00+08:00',
      actor_name: CHLOE,
      details: {
        field: 'registration_capacity',
        previous_value: null,
        new_value: 80,
        significant: false,
      },
    },
  ],
}

/** An event's registrations as the mock keeps them, and the capacity the coordinator set. */
export interface MockRegistrations {
  capacity: number | null
  /** Saved out of order, so the mock must sort them as the backend does, oldest first. */
  registrants: readonly Registrant[]
}

export const MOCK_REGISTRATIONS: Readonly<Record<string, MockRegistrations>> = {
  'EVR-BOOK0102': {
    capacity: 80,
    registrants: [
      {
        name: 'Ravi Kumar',
        email: 'ravi.kumar@example.com',
        registered_at: '2026-10-07T18:40:00+08:00',
        status: 'registered',
      },
      {
        name: 'Hannah Lee',
        email: 'hannah.lee@example.com',
        registered_at: '2026-10-06T09:15:00+08:00',
        status: 'registered',
      },
      {
        name: 'Mei Ling Tan',
        email: 'meiling.tan@example.com',
        registered_at: '2026-10-08T12:05:00+08:00',
        status: 'registered',
      },
      {
        // Withdrew later (SCRUM-53): still listed, but no longer takes a place.
        name: 'Owen Teo',
        email: 'owen.teo@example.com',
        registered_at: '2026-10-07T08:00:00+08:00',
        status: 'withdrawn',
      },
    ],
  },
}
