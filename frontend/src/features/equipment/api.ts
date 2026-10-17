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
  TYPES: '/api/equipment/types',
  AVAILABILITY: (reference: string) => `${eventPath(reference)}/availability`,
  RESERVATIONS: (reference: string) => `${eventPath(reference)}/reservations`,
  LINES: linesPath,
  LINE: (reference: string, lineId: number) => `${linesPath(reference)}/${lineId}`,
} as const

/** An equipment type in the catalogue (SCRUM-27). */
export interface EquipmentType {
  id: number
  name: string
  description: string | null
  total_quantity: number
  venue_id: number | null
  store_name: string | null
}

/** What is free of one equipment type for the event's own period, against what it asks for. */
export interface EquipmentAvailability {
  equipment_type_id: number
  equipment_type_name: string
  available: number
  requested: number
  shortfall: number
}

/** How far Technical Support have got in preparing a reservation (SCRUM-85). */
export type PreparationStatus = 'not_started' | 'in_progress' | 'ready'

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
  /** Technical Support's progress in preparing the units, and their notes (SCRUM-85). */
  preparation_status: PreparationStatus
  preparation_notes: string | null
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

export const equipmentKeys = {
  all: ['equipment'] as const,
  /** The catalogue's equipment types: the same for every member of staff. */
  types: () => [...equipmentKeys.all, 'types'] as const,
  /** Everything about one event's equipment: a change to it can change every list below. */
  event: (reference: string) => [...equipmentKeys.all, 'event', reference] as const,
  availability: (reference: string) => [...equipmentKeys.event(reference), 'availability'] as const,
  reservations: (reference: string) => [...equipmentKeys.event(reference), 'reservations'] as const,
  /** A coordinator reads only their own event's lines, so the answer depends on who asks. */
  lines: (reference: string, viewerId: number | null) =>
    [...equipmentKeys.event(reference), 'lines', viewerId] as const,
}

export function fetchEquipmentTypes(): Promise<EquipmentType[]> {
  return apiRequest<EquipmentType[]>(EQUIPMENT_PATHS.TYPES)
}

export function fetchEventAvailability(reference: string): Promise<EquipmentAvailability[]> {
  return apiRequest<EquipmentAvailability[]>(EQUIPMENT_PATHS.AVAILABILITY(reference))
}

export function fetchEventReservations(reference: string): Promise<EquipmentReservation[]> {
  return apiRequest<EquipmentReservation[]>(EQUIPMENT_PATHS.RESERVATIONS(reference))
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
