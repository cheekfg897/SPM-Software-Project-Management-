// Relative imports, not `@/`: the Playwright tests import this file, and they don't know the
// alias. Keep it free of msw for the same reason.
import { EVENT_REQUEST_STATUS } from '../../config/eventStatus'
import type { EventRequestStatus } from '../../config/eventStatus'
import { MOCK_ACCOUNTS } from '../fixtures/accounts'

/**
 * Data for the equipment mock (backend/app/modules/equipment, and the events module's equipment
 * lines). Every mock event shares one period, so a reservation for one lowers what is free for
 * all of them.
 */

export const MOCK_OPEN_EVENT_REFERENCE = 'EVR-MOCK0001'
export const MOCK_CLOSED_EVENT_REFERENCE = 'EVR-MOCK0002'
/** An event assigned to a coordinator other than the mock one, who is refused it. */
export const MOCK_OTHER_COORDINATORS_EVENT_REFERENCE = 'EVR-MOCK0003'
/**
 * The mock coordinator's event whose date has changed since its equipment was reserved, so its
 * reservations await reassessment (SCRUM-60, ADR-0114).
 */
export const MOCK_MOVED_EVENT_REFERENCE = 'EVR-MOCK0004'
/** That other coordinator. No mock account signs in as them. */
const OTHER_COORDINATOR_ID = 15
/**
 * Events the Safety Officer has approved, so their reservations' preparation can be recorded
 * (SCRUM-85 AC5). The open event stands in for one; every other event, including the one in
 * Safety Review, is still waiting for that approval.
 */
export const MOCK_SAFETY_APPROVED_EVENT_REFERENCES: readonly string[] = [
  MOCK_OPEN_EVENT_REFERENCE,
  // Approved again after its date changed, as a change request could leave it (SCRUM-57), so
  // settling its reservations has an approval to withdraw (SCRUM-60 AC10).
  MOCK_MOVED_EVENT_REFERENCE,
]

export const MOCK_EVENT_PERIOD = {
  starts_at: '2026-10-12T19:30:00+08:00',
  ends_at: '2026-10-12T22:00:00+08:00',
}

/** The moved event's old period, which its reservations still hold (SCRUM-60 AC6). */
export const MOCK_OLD_EVENT_PERIOD = {
  starts_at: '2026-10-09T19:30:00+08:00',
  ends_at: '2026-10-09T22:00:00+08:00',
}

/** When the mock records any outcome (SCRUM-48): a fixed moment, so tests can name it. */
export const MOCK_OUTCOME_RECORDED_AT = '2026-10-06T09:15:00+08:00'

/** When the mock records units taken out of service, and put back (SCRUM-47): fixed moments. */
export const MOCK_OUT_OF_SERVICE_RECORDED_AT = '2026-10-07T14:05:00+08:00'
export const MOCK_BACK_IN_SERVICE_AT = '2026-10-08T09:30:00+08:00'

/** The same period as the event's own date and times, written as the backend writes them. */
export const MOCK_EVENT_SCHEDULE = {
  proposed_date: '2026-10-12',
  end_date: '2026-10-12',
  start_time: '19:30:00',
  end_time: '22:00:00',
}

/** An equipment type as the catalogue lists it (SCRUM-27), with what the mock keeps free. */
export interface MockEquipmentType {
  id: number
  name: string
  description: string | null
  total_quantity: number
  venue_id: number | null
  store_name: string | null
  /** Units free for the period before anything is reserved through the mock. */
  free: number
}

/** Kept in the central store, not at a venue (ADR-0014). */
const IN_THE_STORE = { venue_id: null, store_name: 'Main store' }

/**
 * Ten projectors held, four reserved by other events, leaves six free against the eight the open
 * event asks for. Not in name order, so the mock has to sort them as the backend does.
 */
export const MOCK_EQUIPMENT_TYPES: readonly MockEquipmentType[] = [
  {
    id: 1,
    name: 'Projector',
    description: 'Full HD, with HDMI and USB-C.',
    total_quantity: 10,
    ...IN_THE_STORE,
    free: 6,
  },
  {
    id: 2,
    name: 'Microphone',
    description: 'Wireless, handheld.',
    total_quantity: 12,
    // Kept at a venue, not the store, so the catalogue screens show both kinds of place.
    venue_id: 3,
    store_name: null,
    free: 12,
  },
  { id: 3, name: 'Lectern', description: null, total_quantity: 2, ...IN_THE_STORE, free: 2 },
]

export interface MockEvent {
  reference: string
  name: string
  status: EventRequestStatus
  /** The assigned coordinator's account id; only they, of the coordinators, see its equipment. */
  coordinator_id: number | null
}

/** The mock coordinator's event in `status`, e.g. EVR-UNDER_REVIEW, one for every status. */
export function mockStatusEventReference(status: EventRequestStatus): string {
  return `EVR-${status.toUpperCase()}`
}

function eventsInEveryStatus(): MockEvent[] {
  const events: MockEvent[] = []
  for (const status of Object.values(EVENT_REQUEST_STATUS)) {
    events.push({
      reference: mockStatusEventReference(status),
      name: `Planning meeting (${status})`,
      status,
      coordinator_id: MOCK_ACCOUNTS.coordinator.id,
    })
  }
  return events
}

/**
 * Events that exist. The open one is the mock coordinator's and approved; nobody is assigned the
 * closed one, which is over; the third is another coordinator's.
 */
export const MOCK_EVENTS: readonly MockEvent[] = [
  {
    reference: MOCK_OPEN_EVENT_REFERENCE,
    name: 'Annual Partner Summit',
    status: EVENT_REQUEST_STATUS.APPROVED,
    coordinator_id: MOCK_ACCOUNTS.coordinator.id,
  },
  {
    reference: MOCK_CLOSED_EVENT_REFERENCE,
    name: 'Product Launch Evening',
    status: EVENT_REQUEST_STATUS.COMPLETED,
    coordinator_id: null,
  },
  {
    reference: MOCK_OTHER_COORDINATORS_EVENT_REFERENCE,
    name: 'Alumni Dinner',
    status: EVENT_REQUEST_STATUS.SUBMITTED,
    coordinator_id: OTHER_COORDINATOR_ID,
  },
  {
    reference: MOCK_MOVED_EVENT_REFERENCE,
    name: 'Leadership Offsite',
    status: EVENT_REQUEST_STATUS.APPROVED,
    coordinator_id: MOCK_ACCOUNTS.coordinator.id,
  },
  ...eventsInEveryStatus(),
]

/** Where a line stands, as the backend names it (EquipmentLineStatus, SCRUM-48). */
export type MockEquipmentLineStatus =
  'requested' | 'fulfilled' | 'partially_fulfilled' | 'unavailable'

/** One kind of equipment an event needs (SCRUM-37), with Technical Support's outcome, if any. */
export interface MockEquipmentLine {
  id: number
  event_reference: string
  equipment_type_id: number
  quantity: number
  notes: string | null
  status: MockEquipmentLineStatus
  provided_quantity: number | null
  outcome_note: string | null
  reviewed_by: string | null
  reviewed_at: string | null
}

/** The statuses besides the open event's that start with a line on the event in that status. */
const SEEDED_LINE_STATUSES: readonly EventRequestStatus[] = [
  EVENT_REQUEST_STATUS.AWAITING_CLARIFICATION,
  EVENT_REQUEST_STATUS.SAFETY_REVIEW,
  EVENT_REQUEST_STATUS.CONFIRMED,
  EVENT_REQUEST_STATUS.COMPLETED,
  EVENT_REQUEST_STATUS.CANCELLED,
  EVENT_REQUEST_STATUS.REJECTED,
]
/** Ids for those lines: after the open event's, before any added through the mock. */
const FIRST_SEEDED_LINE_ID = 51

/**
 * Two microphones asked for on each of the mock coordinator's events in those statuses, so
 * Technical Support have a line to record an outcome on there, or be refused one on an event that
 * won't run (SCRUM-48 AC8, ADR-0040 decision 15).
 */
function linesOnStatusEvents(): MockEquipmentLine[] {
  const seeded: MockEquipmentLine[] = []
  for (const [index, status] of SEEDED_LINE_STATUSES.entries()) {
    seeded.push({
      id: FIRST_SEEDED_LINE_ID + index,
      event_reference: mockStatusEventReference(status),
      equipment_type_id: 2,
      quantity: 2,
      notes: null,
      status: 'requested',
      provided_quantity: null,
      outcome_note: null,
      reviewed_by: null,
      reviewed_at: null,
    })
  }
  return seeded
}

/**
 * The Partner Summit's lines (EVR-7K2M9QXA, the mock organiser's event that Chloe coordinates),
 * for what its organiser sees of them (SCRUM-37 AC5, SCRUM-48 AC5, ADR-0104): six of ten
 * projectors, with technical notes, an outcome note and a reviewer, microphones not reviewed yet,
 * and a lectern provided in full with an outcome note (optional for a fulfilled line, SCRUM-48
 * AC2). The organiser sees all of it. That event isn't one the equipment pages open.
 */
const PARTNER_SUMMIT_LINES: readonly MockEquipmentLine[] = [
  {
    id: 61,
    event_reference: 'EVR-7K2M9QXA',
    equipment_type_id: 1,
    quantity: 10,
    notes: 'Two at the back of the hall.',
    status: 'partially_fulfilled',
    provided_quantity: 6,
    outcome_note: 'Four are out for repair.',
    reviewed_by: MOCK_ACCOUNTS.technicalSupport.full_name,
    reviewed_at: '2026-10-05T11:00:00+08:00',
  },
  {
    id: 62,
    event_reference: 'EVR-7K2M9QXA',
    equipment_type_id: 2,
    quantity: 4,
    notes: 'Lapel, not handheld.',
    status: 'requested',
    provided_quantity: null,
    outcome_note: null,
    reviewed_by: null,
    reviewed_at: null,
  },
  {
    id: 63,
    event_reference: 'EVR-7K2M9QXA',
    equipment_type_id: 3,
    quantity: 1,
    notes: 'At the front, stage left.',
    status: 'fulfilled',
    provided_quantity: 1,
    outcome_note: 'The spare one, with a reading light.',
    reviewed_by: MOCK_ACCOUNTS.technicalSupport.full_name,
    reviewed_at: '2026-10-05T11:05:00+08:00',
  },
]

/**
 * The moved event's lines (SCRUM-60): three projectors provided in full, whose reservation awaits
 * reassessment, and two lecterns, partially provided until the date change reopened the line
 * (AC12), whose one reserved lectern is still held (ADR-0114 decision 2).
 */
const MOVED_EVENT_LINES: readonly MockEquipmentLine[] = [
  {
    id: 71,
    event_reference: MOCK_MOVED_EVENT_REFERENCE,
    equipment_type_id: 1,
    quantity: 3,
    notes: null,
    status: 'fulfilled',
    provided_quantity: 3,
    outcome_note: null,
    reviewed_by: MOCK_ACCOUNTS.technicalSupport.full_name,
    reviewed_at: '2026-10-02T10:00:00+08:00',
  },
  {
    id: 72,
    event_reference: MOCK_MOVED_EVENT_REFERENCE,
    equipment_type_id: 3,
    quantity: 2,
    notes: null,
    status: 'requested',
    provided_quantity: null,
    outcome_note: null,
    reviewed_by: null,
    reviewed_at: null,
  },
]

/**
 * The open event's lines. Projectors first, though "Microphone" sorts before it: the backend
 * keeps the order the lines were added. The microphones have been reviewed and will all be
 * provided. Then one line on each event in another status, the Partner Summit's and the moved
 * event's.
 */
export const MOCK_EQUIPMENT_LINES: readonly MockEquipmentLine[] = [
  {
    id: 41,
    event_reference: MOCK_OPEN_EVENT_REFERENCE,
    equipment_type_id: 1,
    quantity: 8,
    notes: 'Ceiling-mounted, with HDMI at the lectern.',
    status: 'requested',
    provided_quantity: null,
    outcome_note: null,
    reviewed_by: null,
    reviewed_at: null,
  },
  {
    id: 42,
    event_reference: MOCK_OPEN_EVENT_REFERENCE,
    equipment_type_id: 2,
    quantity: 4,
    notes: null,
    status: 'fulfilled',
    provided_quantity: 4,
    outcome_note: null,
    reviewed_by: MOCK_ACCOUNTS.technicalSupport.full_name,
    reviewed_at: '2026-10-05T10:00:00+08:00',
  },
  ...linesOnStatusEvents(),
  ...PARTNER_SUMMIT_LINES,
  ...MOVED_EVENT_LINES,
]

/** A reservation the mock starts with: units held for an event (SCRUM-46). */
export interface MockSeededReservation {
  id: number
  event_reference: string
  equipment_type_id: number
  equipment_type_name: string
  quantity: number
  starts_at: string
  ends_at: string
  reserved_by: string
  created_at: string
  /** As config/preparation's PreparationStatus, written out: that file imports with `@/`. */
  preparation_status: 'not_started' | 'in_progress' | 'ready'
  preparation_notes: string | null
  /** A change marked it for Technical Support to reassess (SCRUM-60 AC1, AC8). */
  needs_reassessment: boolean
}

/**
 * The moved event's reservations, still held for its old period and marked for reassessment
 * (SCRUM-60 AC1, AC6). Their ids are past any the mock gives a new reservation in a test.
 */
export const MOCK_SEEDED_RESERVATIONS: readonly MockSeededReservation[] = [
  {
    id: 901,
    event_reference: MOCK_MOVED_EVENT_REFERENCE,
    equipment_type_id: 1,
    equipment_type_name: 'Projector',
    quantity: 3,
    ...MOCK_OLD_EVENT_PERIOD,
    reserved_by: MOCK_ACCOUNTS.technicalSupport.full_name,
    created_at: '2026-10-02T09:00:00+08:00',
    preparation_status: 'in_progress',
    preparation_notes: 'Bulbs checked.',
    needs_reassessment: true,
  },
  {
    id: 902,
    event_reference: MOCK_MOVED_EVENT_REFERENCE,
    equipment_type_id: 3,
    equipment_type_name: 'Lectern',
    quantity: 1,
    ...MOCK_OLD_EVENT_PERIOD,
    reserved_by: MOCK_ACCOUNTS.technicalSupport.full_name,
    created_at: '2026-10-02T09:05:00+08:00',
    preparation_status: 'not_started',
    preparation_notes: null,
    needs_reassessment: true,
  },
]
