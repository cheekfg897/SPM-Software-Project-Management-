import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import type { PreparationStatus } from '@/config/preparation'

import { eventForStaff } from './equipmentAccess'
import {
  MOCK_EQUIPMENT_TYPES,
  MOCK_EVENT_PERIOD,
  MOCK_SEEDED_RESERVATIONS,
} from './equipmentFixtures'
import type { MockEquipmentType } from './equipmentFixtures'
import { outOfServiceQuantity } from './equipmentOutOfServiceEntries'

/**
 * The equipment reserved for events (SCRUM-46), kept in memory until resetMockReservations: the
 * backend's equipment_reservations. The equipment mock answers its routes from here, and the
 * equipment-line mock, the out-of-service mock and the event records read it, so it sits apart
 * from all of them. Every mock event's period now is the one shared period, MOCK_EVENT_PERIOD; a
 * reservation a date change marked still holds its old one (SCRUM-60, ADR-0114).
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
  /** A change marked it for Technical Support to reassess (SCRUM-60 AC1, AC8). Never shown. */
  needs_reassessment: boolean
}

/** One type's marked reservations, as GET .../reassessments answers it (SCRUM-60 AC2). */
export interface MockReassessment {
  equipment_type_id: number
  equipment_type_name: string
  reservations: ReturnType<typeof asShown>[]
  reserved_quantity: number
  starts_at: string
  ends_at: string
  available: number
  shortfall: number
}

let reservations: MockReservation[] = []
/** The event each reservation is for, by reservation id: the backend's foreign key. */
let reservationEvents = new Map<number, string>()
let nextReservationId = 1

/** Start again from the seeded reservations. Runs after every test, with resetMockEquipment. */
export function resetMockReservations(): void {
  reservations = []
  reservationEvents = new Map()
  nextReservationId = 1
  for (const { event_reference: reference, ...seeded } of MOCK_SEEDED_RESERVATIONS) {
    reservations.push({ ...seeded })
    reservationEvents.set(seeded.id, reference)
  }
}

resetMockReservations()

/** Save a new reservation for the event, unmarked, numbered after the ones before it. */
export function saveReservation(
  reference: string,
  fields: Omit<MockReservation, 'id' | 'needs_reassessment'>,
): MockReservation {
  const reservation: MockReservation = {
    id: nextReservationId,
    ...fields,
    needs_reassessment: false,
  }
  nextReservationId += 1
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

/** Whether it overlaps the shared period, as `_overlapping` compares them. */
function isInThePeriodNow(reservation: MockReservation): boolean {
  const startsBeforeTheEnd =
    Date.parse(reservation.starts_at) < Date.parse(MOCK_EVENT_PERIOD.ends_at)
  const endsAfterTheStart =
    Date.parse(reservation.ends_at) > Date.parse(MOCK_EVENT_PERIOD.starts_at)
  return startsBeforeTheEnd && endsAfterTheStart
}

function reservedQuantity(equipmentTypeId: number): number {
  let total = 0
  for (const reservation of reservations) {
    if (reservation.equipment_type_id === equipmentTypeId && isInThePeriodNow(reservation)) {
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

/** The events holding a reservation of the type for the period now, by reference, each once. */
export function eventsReservingType(equipmentTypeId: number): string[] {
  const references: string[] = []
  for (const reservation of reservations) {
    const reference = reservationEvents.get(reservation.id)
    const reservesType =
      reservation.equipment_type_id === equipmentTypeId && isInThePeriodNow(reservation)
    if (reservesType && reference !== undefined && !references.includes(reference)) {
      references.push(reference)
    }
  }
  return references
}

/**
 * The reservation as the API shows it, with its flag (SCRUM-47 AC3): units out of service have
 * left fewer in service than are reserved for the period. Every mock event shares one period, so
 * every reservation of that type held for it is flagged, and the mock does not compare the period
 * with today. The backend saves the flag when units go out or come back; reserving can't leave a
 * type short, so working it out here gives the same answer. Whether it awaits reassessment is not
 * shown: its type's reassessment says so (SCRUM-60).
 */
export function asShown(reservation: MockReservation) {
  return {
    id: reservation.id,
    equipment_type_id: reservation.equipment_type_id,
    equipment_type_name: reservation.equipment_type_name,
    quantity: reservation.quantity,
    starts_at: reservation.starts_at,
    ends_at: reservation.ends_at,
    reserved_by: reservation.reserved_by,
    created_at: reservation.created_at,
    needs_attention: isInThePeriodNow(reservation) && isTypeShort(reservation.equipment_type_id),
    preparation_status: reservation.preparation_status,
    preparation_notes: reservation.preparation_notes,
  }
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

// --------------------------------------------------------------------------
// SCRUM-60: reservations a change marked for reassessment (ADR-0114)
// --------------------------------------------------------------------------

/** The event's reservations of the type that a change marked, oldest first. */
function reservationsToReassess(reference: string, equipmentTypeId: number): MockReservation[] {
  return reservationsOfEvent(reference).filter(
    (reservation) =>
      reservation.equipment_type_id === equipmentTypeId && reservation.needs_reassessment,
  )
}

/** Units the reservations hold between them. */
function unitsHeld(held: MockReservation[]): number {
  let total = 0
  for (const reservation of held) {
    total += reservation.quantity
  }
  return total
}

/**
 * Units of the type free for the period now, the event's marked reservations aside: they are the
 * units being reassessed (`_free_for_reassessment`).
 */
function freeForReassessment(reference: string, type: MockEquipmentType): number {
  const beingReassessed = unitsHeld(
    reservationsToReassess(reference, type.id).filter(isInThePeriodNow),
  )
  const takenByOthers = reservedQuantity(type.id) - beingReassessed
  return Math.max(type.free - takenByOthers - outOfServiceQuantity(type.id), 0)
}

/** A new quantity on the line marks the event's reservations of its type (SCRUM-60 AC8). */
export function markReservationsOfType(reference: string, equipmentTypeId: number): void {
  for (const reservation of reservationsOfEvent(reference)) {
    if (reservation.equipment_type_id === equipmentTypeId) {
      reservation.needs_reassessment = true
    }
  }
}

/** Whether the event has a reservation of the type marked for reassessment. */
export function hasReservationsToReassess(reference: string, equipmentTypeId: number): boolean {
  return reservationsToReassess(reference, equipmentTypeId).length > 0
}

/** The event's marked reservations, one entry per type by name, with any shortfall (AC2). */
export function reassessmentsOf(reference: string): MockReassessment[] {
  const byName = [...MOCK_EQUIPMENT_TYPES].sort((first, second) =>
    first.name.localeCompare(second.name),
  )
  const reassessments: MockReassessment[] = []
  for (const type of byName) {
    const held = reservationsToReassess(reference, type.id)
    if (held.length === 0) {
      continue
    }
    const reserved = unitsHeld(held)
    const available = freeForReassessment(reference, type)
    reassessments.push({
      equipment_type_id: type.id,
      equipment_type_name: type.name,
      reservations: held.map(asShown),
      reserved_quantity: reserved,
      ...MOCK_EVENT_PERIOD,
      available,
      shortfall: Math.max(reserved - available, 0),
    })
  }
  return reassessments
}

/**
 * Why the marked reservations of the type can't keep `provided` of their units for the period
 * now, in the backend's words, or undefined when they can or none is marked
 * (`settle_reassessment`).
 */
export function refusalToSettle(
  reference: string,
  equipmentTypeId: number,
  provided: number,
): string | undefined {
  const reassessment = reassessmentsOf(reference).find(
    (row) => row.equipment_type_id === equipmentTypeId,
  )
  if (reassessment === undefined) {
    return undefined
  }
  const keep = Math.min(provided, reassessment.reserved_quantity)
  const { available } = reassessment
  if (keep <= available) {
    return undefined
  }
  return `${reassessment.equipment_type_name}: only ${String(available)} free for the event's period, not the ${String(keep)} to keep. Record an outcome that provides no more than ${String(available)}.`
}

/**
 * Keep `provided` of the marked reservations' units, oldest first, for the period now, and
 * release the rest (SCRUM-60 AC3, AC4, AC9). The caller has checked refusalToSettle.
 */
export function settleReassessment(
  reference: string,
  equipmentTypeId: number,
  provided: number,
): void {
  const held = reservationsToReassess(reference, equipmentTypeId)
  let leftToKeep = Math.min(provided, unitsHeld(held))
  for (const reservation of held) {
    if (leftToKeep === 0) {
      reservations = reservations.filter((candidate) => candidate !== reservation)
      continue
    }
    reservation.quantity = Math.min(reservation.quantity, leftToKeep)
    leftToKeep -= reservation.quantity
    reservation.starts_at = MOCK_EVENT_PERIOD.starts_at
    reservation.ends_at = MOCK_EVENT_PERIOD.ends_at
    reservation.needs_reassessment = false
  }
}

/** The event's units held of the type, whatever their period (`_event_reserved_quantity`). */
export function unitsReservedForEvent(reference: string, equipmentTypeId: number): number {
  return unitsHeld(
    reservationsOfEvent(reference).filter(
      (reservation) => reservation.equipment_type_id === equipmentTypeId,
    ),
  )
}
