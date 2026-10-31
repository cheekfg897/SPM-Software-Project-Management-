import type { PreparationStatus, PreparationUpdate } from '@/config/preparation'
import { apiRequest } from '@/lib/api'

/** One event's equipment, by its EVR- reference, escaped so it stays one path segment. */
function eventPath(reference: string): string {
  return `/api/equipment/events/${encodeURIComponent(reference)}`
}

/** One event request's equipment lines, by its EVR- reference, escaped the same way. */
function linesPath(reference: string): string {
  return `/api/events/requests/${encodeURIComponent(reference)}/equipment`
}

/**
 * The equipment API: backend/app/modules/equipment/routes.py, and the events module's equipment
 * lines (backend/app/modules/events/routes.py, SCRUM-37). Events are named by EVR- reference.
 */
const EQUIPMENT_PATHS = {
  AVAILABILITY: (reference: string) => `${eventPath(reference)}/availability`,
  RESERVATIONS: (reference: string) => `${eventPath(reference)}/reservations`,
  REASSESSMENTS: (reference: string) => `${eventPath(reference)}/reassessments`,
  CONFIRM_REASSESSMENT: (reference: string, equipmentTypeId: number) =>
    `${eventPath(reference)}/reassessments/${equipmentTypeId}/confirm`,
  LINES: linesPath,
  LINE: (reference: string, lineId: number) => `${linesPath(reference)}/${lineId}`,
  OUTCOME: (reference: string, lineId: number) => `${linesPath(reference)}/${lineId}/outcome`,
  preparationFor: (reservationId: number) =>
    `/api/equipment/reservations/${reservationId}/preparation`,
} as const

/** An equipment type: the catalogue's (SCRUM-27), which the lines are named from. */
export type { EquipmentType } from '@/features/equipmentCatalogue/api'

/** What is free of one equipment type for the event's own period, against what it asks for. */
export interface EquipmentAvailability {
  equipment_type_id: number
  equipment_type_name: string
  available: number
  requested: number
  shortfall: number
}

/** Equipment held for an event. `reserved_by` is the reserver's name, null once their account is gone. */
export interface EquipmentReservation {
  id: number
  equipment_type_id: number
  equipment_type_name: string
  quantity: number
  /** ISO date-time with an offset, in business time. */
  starts_at: string
  ends_at: string
  reserved_by: string | null
  created_at: string
  /** Units out of service have left the type short of what is reserved (SCRUM-47 AC3). */
  needs_attention: boolean
  /** Technical Support's progress in preparing the units, and their notes (SCRUM-85). */
  preparation_status: PreparationStatus
  preparation_notes: string | null
}

/**
 * One equipment type's reservations marked for reassessment after the event's date, time or line
 * quantity changed (SCRUM-60 AC2, ADR-0114): what they hold, still for their own period, against
 * what is free for the event's period now. The shortfall is what that period can't give.
 */
export interface ReservationReassessment {
  equipment_type_id: number
  equipment_type_name: string
  /** The marked reservations, oldest first, each with the period it still holds. */
  reservations: EquipmentReservation[]
  reserved_quantity: number
  /** The event's period now, which confirming moves them to (ISO date-times with an offset). */
  starts_at: string
  ends_at: string
  available: number
  shortfall: number
  /**
   * Whether confirming would settle them now (ADR-0114 decision 23). If not, the line's outcome
   * settles them instead (AC4, AC8, AC12).
   */
  confirmable: boolean
}

export interface ReserveEquipmentBody {
  equipment_type_id: number
  quantity: number
}

/** Where a line stands: `requested` until Technical Support record their review (SCRUM-48). */
export type EquipmentLineStatus = 'requested' | 'fulfilled' | 'partially_fulfilled' | 'unavailable'

/** One kind of equipment an event needs, as adding or changing it answers (SCRUM-37). */
export interface SavedEquipmentLine {
  id: number
  equipment_type_id: number
  quantity: number
  /** Technical notes for Technical Support; null when there are none. */
  notes: string | null
  status: EquipmentLineStatus
}

/** A line as the event's list shows it to staff, with Technical Support's outcome (SCRUM-48). */
export interface EquipmentLine extends SavedEquipmentLine {
  provided_quantity: number | null
  shortfall: number | null
  outcome_note: string | null
  reviewed_by: string | null
  reviewed_at: string | null
}

/** The event the lines belong to, and when it is: when the equipment is needed by. */
export interface EquipmentLinesEvent {
  reference: string
  name: string
  proposed_date: string
  end_date: string
  start_time: string
  end_time: string
}

/** An event's equipment lines, in the order they were added. */
export interface EventEquipmentLines {
  event: EquipmentLinesEvent
  equipment_lines: EquipmentLine[]
}

/**
 * What adding or changing a line sends. Adding needs the type and quantity; a change sends only
 * the fields that changed. A cleared field is sent as null, and the backend says why it can't be.
 */
export interface EquipmentLineBody {
  equipment_type_id?: number | null
  quantity?: number | null
  notes?: string
}

export interface EquipmentLineChange {
  lineId: number
  body: EquipmentLineBody
}

/**
 * What recording a line's outcome sends (SCRUM-48): how many units will be provided, and the
 * note for the coordinator. A blank field is not sent, so the backend says what is missing; the
 * status is never sent, since it follows from the quantity (ADR-0040).
 */
export interface EquipmentOutcomeBody {
  provided_quantity?: number
  note?: string
}

export interface EquipmentOutcomeChange {
  lineId: number
  body: EquipmentOutcomeBody
}

export const equipmentKeys = {
  all: ['equipment'] as const,
  /** Everything about one event's equipment: a change to it can change every list below. */
  event: (reference: string) => [...equipmentKeys.all, 'event', reference] as const,
  availability: (reference: string) => [...equipmentKeys.event(reference), 'availability'] as const,
  reservations: (reference: string) => [...equipmentKeys.event(reference), 'reservations'] as const,
  reassessments: (reference: string) =>
    [...equipmentKeys.event(reference), 'reassessments'] as const,
  /** A coordinator reads only their own event's lines, so the answer depends on who asks. */
  lines: (reference: string, viewerId: number | null) =>
    [...equipmentKeys.event(reference), 'lines', viewerId] as const,
}

export function fetchEventAvailability(reference: string): Promise<EquipmentAvailability[]> {
  return apiRequest<EquipmentAvailability[]>(EQUIPMENT_PATHS.AVAILABILITY(reference))
}

export function fetchEventReservations(reference: string): Promise<EquipmentReservation[]> {
  return apiRequest<EquipmentReservation[]>(EQUIPMENT_PATHS.RESERVATIONS(reference))
}

/** What a change left to reassess of the event's reservations (SCRUM-60). */
export function fetchEventReassessments(reference: string): Promise<ReservationReassessment[]> {
  return apiRequest<ReservationReassessment[]>(EQUIPMENT_PATHS.REASSESSMENTS(reference))
}

/**
 * Confirm one type's marked reservations for the event's period now (SCRUM-60 AC3). Technical
 * Support Staff only. Answers the type's reservations as they now stand.
 */
export function confirmReassessment(
  reference: string,
  equipmentTypeId: number,
): Promise<EquipmentReservation[]> {
  return apiRequest<EquipmentReservation[]>(
    EQUIPMENT_PATHS.CONFIRM_REASSESSMENT(reference, equipmentTypeId),
    { method: 'POST' },
  )
}

/** Reserve units of one equipment type for the event. Technical Support Staff only. */
export function reserveEquipment(
  reference: string,
  body: ReserveEquipmentBody,
): Promise<EquipmentReservation> {
  return apiRequest<EquipmentReservation>(EQUIPMENT_PATHS.RESERVATIONS(reference), {
    method: 'POST',
    body,
  })
}

/** The event's equipment lines. Technical Support, and the event's assigned coordinator. */
export function fetchEventEquipmentLines(reference: string): Promise<EventEquipmentLines> {
  return apiRequest<EventEquipmentLines>(EQUIPMENT_PATHS.LINES(reference))
}

/** Add a line to the event. Its assigned coordinator only. */
export function addEquipmentLine(
  reference: string,
  body: EquipmentLineBody,
): Promise<SavedEquipmentLine> {
  return apiRequest<SavedEquipmentLine>(EQUIPMENT_PATHS.LINES(reference), {
    method: 'POST',
    body,
  })
}

/** Change the fields sent on one of the event's lines. Its assigned coordinator only. */
export function updateEquipmentLine(
  reference: string,
  { lineId, body }: EquipmentLineChange,
): Promise<SavedEquipmentLine> {
  return apiRequest<SavedEquipmentLine>(EQUIPMENT_PATHS.LINE(reference, lineId), {
    method: 'PATCH',
    body,
  })
}

/** Remove one of the event's lines. Its assigned coordinator only. */
export function removeEquipmentLine(reference: string, lineId: number): Promise<void> {
  return apiRequest<void>(EQUIPMENT_PATHS.LINE(reference, lineId), { method: 'DELETE' })
}

/** Record or revise the outcome of one of the event's lines. Technical Support Staff only. */
export function recordEquipmentOutcome(
  reference: string,
  { lineId, body }: EquipmentOutcomeChange,
): Promise<EquipmentLine> {
  return apiRequest<EquipmentLine>(EQUIPMENT_PATHS.OUTCOME(reference, lineId), {
    method: 'POST',
    body,
  })
}

/** Record a reservation's preparation status and notes (SCRUM-85). Technical Support Staff only. */
export function updateReservationPreparation(
  reservationId: number,
  update: PreparationUpdate,
): Promise<EquipmentReservation> {
  return apiRequest<EquipmentReservation>(EQUIPMENT_PATHS.preparationFor(reservationId), {
    method: 'PUT',
    body: update,
  })
}
