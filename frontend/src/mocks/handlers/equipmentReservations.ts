import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import type { PreparationStatus } from '@/config/preparation'

import { eventForStaff } from './equipmentAccess'
import { MOCK_EQUIPMENT_TYPES } from './equipmentFixtures'
import { outOfServiceQuantity } from './equipmentOutOfServiceEntries'

/**
 * The equipment reserved for events (SCRUM-46), kept in memory until resetMockReservations: the
 * backend's equipment_reservations. The equipment mock answers its routes from here, and the
 * equipment-line mock, the out-of-service mock and the event records read it, so it sits apart
 * from all of them.
 */

export interface MockReservation {
  id: number
  equipment_type_id: number
  equipment_type_name: string
  quantity: number
  starts_at: string
  ends_at: string
  reserved_by: string
  created_at: string
  preparation_status: PreparationStatus
  preparation_notes: string | null
}

let reservations: MockReservation[] = []
/** The event each reservation is for, by reservation id: the backend's foreign key. */
let reservationEvents = new Map<number, string>()

/** Forget every reservation. Runs after every test, with resetMockEquipment. */
export function resetMockReservations(): void {
  reservations = []
  reservationEvents = new Map()
}

/** Save a new reservation for the event, numbered after the ones before it. */
export function saveReservation(
  reference: string,
  fields: Omit<MockReservation, 'id'>,
): MockReservation {
  const reservation: MockReservation = { id: reservations.length + 1, ...fields }
  reservations.push(reservation)
  reservationEvents.set(reservation.id, reference)
  return reservation
}

/** The reservation with that id, or undefined. */
export function reservationWithId(reservationId: number): MockReservation | undefined {
  return reservations.find((saved) => saved.id === reservationId)
}

/** The reference of the event a reservation is for. */
export function eventOfReservation(reservation: MockReservation): string {
  return reservationEvents.get(reservation.id) ?? ''
}

/** The event's reservations, oldest first. */
export function reservationsOfEvent(reference: string): MockReservation[] {
  return reservations.filter((reservation) => reservationEvents.get(reservation.id) === reference)
}

/**
 * The event, rejected during planning, gives back its equipment as the backend's
 * release_event_reservations does (SCRUM-49 AC10, ADR-0093): its reservations go, and its
 * status closes its open lines to outcomes and reservations (EQUIPMENT_NOT_NEEDED_STATUSES).
 */
export function rejectEventEquipment(reference: string): void {
  const event = eventForStaff(reference)
  if (event === undefined) {
    return
  }
  event.status = EVENT_REQUEST_STATUS.REJECTED
  reservations = reservations.filter(
    (reservation) => reservationEvents.get(reservation.id) !== reference,
  )
}

function reservedQuantity(equipmentTypeId: number): number {
  let total = 0
  for (const reservation of reservations) {
    if (reservation.equipment_type_id === equipmentTypeId) {
      total += reservation.quantity
    }
  }
  return total
}

/** What is left of `free` once this mock's reservations and the units out of service are taken. */
function unreservedQuantity(equipmentTypeId: number, free: number): number {
  return free - reservedQuantity(equipmentTypeId) - outOfServiceQuantity(equipmentTypeId)
}

export function availableQuantity(equipmentTypeId: number, free: number): number {
  return Math.max(unreservedQuantity(equipmentTypeId, free), 0)
}

/** Whether the type has fewer units in service than are reserved for the period (SCRUM-47). */
export function isTypeShort(equipmentTypeId: number): boolean {
  const type = MOCK_EQUIPMENT_TYPES.find((candidate) => candidate.id === equipmentTypeId)
  return type !== undefined && unreservedQuantity(type.id, type.free) < 0
}

/** The events holding a reservation of the type, by reference, each once. */
export function eventsReservingType(equipmentTypeId: number): string[] {
  const references: string[] = []
  for (const reservation of reservations) {
    const reference = reservationEvents.get(reservation.id)
    const reservesType = reservation.equipment_type_id === equipmentTypeId
    if (reservesType && reference !== undefined && !references.includes(reference)) {
      references.push(reference)
    }
  }
  return references
}

/**
 * The reservation with its flag (SCRUM-47 AC3): units out of service have left fewer in service
 * than are reserved for the period. Every mock event shares one period, so every reservation of
 * that type is flagged, and the mock does not compare the period with today. The backend saves
 * the flag when units go out or come back; reserving can't leave a type short, so working it out
 * here gives the same answer.
 */
export function asShown(reservation: MockReservation) {
  return { ...reservation, needs_attention: isTypeShort(reservation.equipment_type_id) }
}

/**
 * The event's reservations, oldest first, as the read-only staff record shows them: no ids, and
 * Technical Support's preparation on each (list_reservations_of_event, SCRUM-85 AC2, ADR-0095).
 */
export function reservationsForRecord(reference: string) {
  return reservationsOfEvent(reference).map((reservation) => ({
    equipment_type_name: reservation.equipment_type_name,
    quantity: reservation.quantity,
    starts_at: reservation.starts_at,
    ends_at: reservation.ends_at,
    reserved_by: reservation.reserved_by,
    preparation_status: reservation.preparation_status,
    preparation_notes: reservation.preparation_notes,
  }))
}
