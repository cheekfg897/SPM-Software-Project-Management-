import type { EventListRow } from '@/features/eventRequests/api'
import type { EquipmentLine } from '@/features/techSupport/api'

import { MOCK_CLOSED_EVENT_REFERENCE, MOCK_OPEN_EVENT_REFERENCE } from './equipmentFixtures'

/**
 * The events Technical Support's two lists are read from (SCRUM-38, SCRUM-24 AC5; ADR-0061),
 * with their equipment lines. Projector is equipment type 1 and Microphone type 2, as in the
 * equipment mock. The queue's "today" is the mock's, MOCK_TODAY (2026-10-05).
 */

/** An event as the mock stores it for these lists. */
export interface MockEquipmentEvent {
  /** The backend's id: the queue's last tie-breaker, "as submitted" (ADR-0022). Never shown. */
  id: number
  /** When it was submitted: the newest-first order of the events with equipment. Never shown. */
  createdAt: string
  /** Always dated, with a start: a draft, the only request without, never has equipment. */
  event: EventListRow & { proposed_date: string; start_time: string }
  lines: EquipmentLine[]
}

const PROJECTOR = 1
const MICROPHONE = 2

/** A line still waiting for Technical Support. Ids are the event's id and the line's place. */
function requested(id: number, equipmentTypeId: number, quantity: number): EquipmentLine {
  return { id, equipment_type_id: equipmentTypeId, quantity, notes: null, status: 'requested' }
}

/** An event that runs from `start` to `end` on `date`. */
function on(date: string, start: string, end: string) {
  return { proposed_date: date, end_date: date, start_time: start, end_time: end }
}

/**
 * Stored out of the queue's order, with decoys where a leak would show early: a cancelled, a
 * completed and a rejected event dated just after today, yesterday's event, an event whose lines
 * are all dealt with, and the newest event, which has no equipment at all. Two events share a
 * date and a start, the higher id stored first; a third that day starts earlier with a higher id.
 */
export const MOCK_EQUIPMENT_EVENTS: readonly MockEquipmentEvent[] = [
  {
    id: 31,
    createdAt: '2026-09-27T03:00:00+00:00',
    event: {
      reference: 'EVR-BOOK0102',
      name: 'Year-End Town Hall',
      status: 'confirmed',
      ...on('2026-11-10', '09:00:00', '17:00:00'),
    },
    lines: [requested(311, MICROPHONE, 8)],
  },
  {
    id: 47,
    createdAt: '2026-10-07T09:00:00+00:00',
    event: {
      reference: 'EVR-TECH0007',
      name: 'Long-Service Awards',
      status: 'confirmed',
      ...on('2026-10-04', '18:00:00', '21:00:00'),
    },
    lines: [requested(471, PROJECTOR, 3)],
  },
  {
    id: 23,
    createdAt: '2026-10-01T03:00:00+00:00',
    event: {
      reference: MOCK_OPEN_EVENT_REFERENCE,
      name: 'Evening Product Showcase',
      status: 'approved',
      ...on('2026-10-12', '19:30:00', '22:00:00'),
    },
    lines: [requested(231, PROJECTOR, 2), requested(232, MICROPHONE, 4)],
  },
  {
    id: 44,
    createdAt: '2026-10-02T06:05:00+00:00',
    event: {
      reference: MOCK_CLOSED_EVENT_REFERENCE,
      name: 'Product Launch Evening',
      status: 'cancelled',
      ...on('2026-10-06', '18:00:00', '21:30:00'),
    },
    lines: [requested(441, PROJECTOR, 5)],
  },
  {
    id: 29,
    createdAt: '2026-10-04T03:00:00+00:00',
    event: {
      reference: 'EVR-BOOK0101',
      name: 'Harbourfront Careers Fair',
      status: 'approved',
      ...on('2026-11-10', '09:00:00', '17:00:00'),
    },
    lines: [
      { ...requested(291, PROJECTOR, 1), status: 'fulfilled' },
      requested(292, MICROPHONE, 6),
    ],
  },
  {
    id: 52,
    createdAt: '2026-10-03T01:00:00+00:00',
    event: {
      reference: 'EVR-TECH0001',
      name: 'Sunrise Wellness Walk',
      status: 'submitted',
      ...on('2026-10-05', '07:00:00', '09:00:00'),
    },
    lines: [requested(521, MICROPHONE, 1)],
  },
  {
    id: 45,
    createdAt: '2026-10-05T09:00:00+00:00',
    event: {
      reference: 'EVR-TECH0005',
      name: 'Graduation Dinner',
      status: 'completed',
      ...on('2026-10-07', '19:00:00', '22:00:00'),
    },
    lines: [requested(451, MICROPHONE, 2)],
  },
  {
    id: 46,
    createdAt: '2026-10-06T09:00:00+00:00',
    event: {
      reference: 'EVR-TECH0006',
      name: 'Rooftop Film Night',
      status: 'rejected',
      ...on('2026-10-08', '20:00:00', '23:00:00'),
    },
    lines: [requested(461, PROJECTOR, 1)],
  },
  {
    id: 35,
    createdAt: '2026-09-28T02:00:00+00:00',
    event: {
      reference: 'EVR-TECH0002',
      name: 'Data Science Meetup',
      status: 'under_review',
      ...on('2026-10-30', '18:00:00', '21:00:00'),
    },
    lines: [requested(351, PROJECTOR, 1)],
  },
  {
    id: 36,
    createdAt: '2026-09-29T02:00:00+00:00',
    event: {
      reference: 'EVR-TECH0003',
      name: 'Charity Fun Run',
      status: 'awaiting_clarification',
      ...on('2026-11-03', '07:00:00', '11:00:00'),
    },
    lines: [requested(361, MICROPHONE, 10)],
  },
  {
    id: 38,
    createdAt: '2026-09-30T02:00:00+00:00',
    event: {
      reference: 'EVR-TECH0004',
      name: 'Board Breakfast Briefing',
      status: 'submitted',
      ...on('2026-11-10', '07:30:00', '09:00:00'),
    },
    lines: [requested(381, PROJECTOR, 2)],
  },
  {
    id: 21,
    createdAt: '2026-10-06T02:00:00+00:00',
    event: {
      reference: 'EVR-7K2M9QXA',
      name: 'Partner Summit',
      status: 'under_review',
      ...on('2026-11-12', '09:00:00', '17:00:00'),
    },
    lines: [
      { ...requested(211, PROJECTOR, 4), status: 'partially_fulfilled' },
      { ...requested(212, MICROPHONE, 9), status: 'unavailable' },
      { ...requested(213, PROJECTOR, 1), status: 'fulfilled' },
    ],
  },
  {
    id: 50,
    createdAt: '2026-10-08T00:00:00+00:00',
    event: {
      reference: 'EVR-TECH0008',
      name: 'Volunteer Briefing',
      status: 'submitted',
      ...on('2026-10-09', '10:00:00', '11:00:00'),
    },
    lines: [],
  },
]
