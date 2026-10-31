import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'

import { EQUIPMENT_READER_ROLES, ROLE } from '@/config/roles'
import type { PreparationStatus } from '@/config/preparation'
import { isRecord } from '@/lib/isRecord'

import { errorResponse, readBody, validationError } from '../responses'

import {
  callerOrRefusal,
  EQUIPMENT_NOT_NEEDED_STATUSES,
  eventForReader,
  eventForStaff,
  eventNotFound,
  hasSafetyApproval,
  resetMockEquipmentEvents,
  withdrawSafetyApproval,
} from './equipmentAccess'
import { idFromPath, routeNotFound } from './equipmentCatalogue'
import { MOCK_EQUIPMENT_TYPES, MOCK_EVENT_PERIOD } from './equipmentFixtures'
import type { MockEquipmentType } from './equipmentFixtures'
import {
  equipmentLineHandlers,
  lineOfType,
  requestedQuantity,
  resetMockEquipmentLines,
} from './equipmentLines'
import { resetMockOutOfService } from './equipmentOutOfServiceEntries'
import {
  asShown,
  availableQuantity,
  eventOfReservation,
  reassessmentsOf,
  refusalToSettle,
  reservationsOfEvent,
  reservationWithId,
  resetMockReservations,
  saveReservation,
  settleReassessment,
  unitsReservedForEvent,
} from './equipmentReservations'
import type { MockReassessment } from './equipmentReservations'
import {
  EQUIPMENT_TYPE_ID_RANGE_MESSAGE,
  MISSING_MESSAGE,
  positiveWholeNumberError,
  QUANTITY_RANGE_MESSAGE,
} from './equipmentValidation'
import {
  PREPARATION_NEEDS_SAFETY_APPROVAL_MESSAGE,
  preparationErrors,
  savedNotes,
} from './preparationRules'

/**
 * The equipment endpoints, as backend/app/modules/equipment/routes.py answers them (SCRUM-45
 * availability, SCRUM-46 reservations, SCRUM-85 preparation), and the events module's equipment
 * lines (SCRUM-37, equipmentLines.ts). Units out of service (SCRUM-47) are answered in
 * equipmentOutOfService.ts and count here; the catalogue's types are answered in
 * equipmentCatalogue.ts. Reservations are kept in equipmentReservations.ts. What a change left
 * to reassess is answered here, and confirmed (SCRUM-60, ADR-0114).
 */

const EVENT_PATH = '/api/equipment/events/:reference'
const RESERVATIONS_CLOSED_MESSAGE =
  "Equipment can't be reserved for an event that is completed, cancelled or rejected."
const NOTHING_TO_REASSESS_MESSAGE =
  'This event has no reservation of that equipment type awaiting reassessment.'
const RECORD_THE_OUTCOME_MESSAGE =
  "This equipment's request has no current outcome. Record its outcome instead: that settles the reservation."

/** Forget every reservation, line change and unit out of service. Runs after every test. */
export function resetMockEquipment(): void {
  resetMockReservations()
  resetMockEquipmentLines()
  resetMockEquipmentEvents()
  resetMockOutOfService()
}

/** Every equipment type, by name, as the backend lists the catalogue. */
function equipmentTypesByName(): MockEquipmentType[] {
  return [...MOCK_EQUIPMENT_TYPES].sort((first, second) => first.name.localeCompare(second.name))
}

/** One row per equipment type, by name, against what this event's lines ask for. */
function availabilityRows(reference: string) {
  return equipmentTypesByName().map((type) => {
    const available = availableQuantity(type.id, type.free)
    const requested = requestedQuantity(reference, type.id)
    return {
      equipment_type_id: type.id,
      equipment_type_name: type.name,
      available,
      requested,
      shortfall: Math.max(requested - available, 0),
    }
  })
}

/**
 * Why reserving `quantity` more of the type would take the event past its line, in the backend's
 * words, or undefined when it wouldn't or the event has no line of the type (SCRUM-60 AC9).
 */
function overTheLine(reference: string, equipmentTypeId: number, quantity: number) {
  const line = lineOfType(reference, equipmentTypeId)
  if (line === undefined) {
    return undefined
  }
  const already = unitsReservedForEvent(reference, equipmentTypeId)
  if (already + quantity <= line.quantity) {
    return undefined
  }
  return `The event asks for ${String(line.quantity)} of these, and ${String(already)} are already reserved.`
}

/**
 * At most how many units confirming keeps of the type's marked reservations
 * (`_quantity_to_confirm`): what the line's outcome provides, null while it has none, or what is
 * free for a type the event has no line for (ADR-0114 decision 22).
 */
function quantityToConfirm(reference: string, reassessment: MockReassessment): number | null {
  const line = lineOfType(reference, reassessment.equipment_type_id)
  if (line === undefined) {
    return reassessment.available
  }
  return line.provided_quantity
}

/**
 * The event's reassessments, each saying whether confirming would settle it now: it keeps no more
 * than is held, and refuses to keep more than is free (`_reassessment_of`, decision 23).
 */
function reassessmentsWithConfirmable(reference: string) {
  return reassessmentsOf(reference).map((reassessment) => {
    const toConfirm = quantityToConfirm(reference, reassessment)
    const confirmable =
      toConfirm !== null &&
      Math.min(toConfirm, reassessment.reserved_quantity) <= reassessment.available
    return { ...reassessment, confirmable }
  })
}

/** Problems with the reservation body, by field, in the backend's wording (EquipmentUnitsSchema). */
function bodyErrors(body: unknown): Record<string, string[]> {
  const sent = isRecord(body) ? body : {}
  const rangeMessages = {
    equipment_type_id: EQUIPMENT_TYPE_ID_RANGE_MESSAGE,
    quantity: QUANTITY_RANGE_MESSAGE,
  }
  const errors: Record<string, string[]> = {}
  for (const [name, rangeMessage] of Object.entries(rangeMessages)) {
    const error =
      sent[name] === undefined
        ? MISSING_MESSAGE
        : positiveWholeNumberError(sent[name], rangeMessage)
    if (error !== undefined) {
      errors[name] = [error]
    }
  }
  return errors
}

export const equipmentHandlers: RequestHandler[] = [
  http.get(`${EVENT_PATH}/availability`, ({ request, params }) => {
    const caller = callerOrRefusal(request, EQUIPMENT_READER_ROLES)
    if (caller instanceof Response) {
      return caller
    }
    const event = eventForReader(caller, String(params.reference))
    if (event === undefined) {
      return eventNotFound()
    }
    return HttpResponse.json(availabilityRows(event.reference))
  }),

  http.get(`${EVENT_PATH}/reservations`, ({ request, params }) => {
    const caller = callerOrRefusal(request, EQUIPMENT_READER_ROLES)
    if (caller instanceof Response) {
      return caller
    }
    const event = eventForReader(caller, String(params.reference))
    if (event === undefined) {
      return eventNotFound()
    }
    return HttpResponse.json(reservationsOfEvent(event.reference).map(asShown))
  }),

  http.post(`${EVENT_PATH}/reservations`, async ({ request, params }) => {
    const caller = callerOrRefusal(request, [ROLE.TECHNICAL_SUPPORT_STAFF])
    if (caller instanceof Response) {
      return caller
    }
    // The backend's order: the body, then the event, then whether it is open, then the type.
    const body: unknown = await request.json()
    const errors = bodyErrors(body)
    if (Object.keys(errors).length > 0) {
      return validationError(errors)
    }
    const event = eventForStaff(String(params.reference))
    if (event === undefined) {
      return eventNotFound()
    }
    if (EQUIPMENT_NOT_NEEDED_STATUSES.includes(event.status)) {
      return errorResponse(409, 'equipment_not_reservable', RESERVATIONS_CLOSED_MESSAGE)
    }

    // bodyErrors has just checked both are whole numbers.
    const { equipment_type_id: typeId, quantity } = body as {
      equipment_type_id: number
      quantity: number
    }
    const type = MOCK_EQUIPMENT_TYPES.find((candidate) => candidate.id === typeId)
    if (type === undefined) {
      return validationError({ equipment_type_id: ['Equipment type not found.'] })
    }
    const pastTheLine = overTheLine(event.reference, type.id, quantity)
    if (pastTheLine !== undefined) {
      return validationError({ quantity: [pastTheLine] })
    }
    const available = availableQuantity(type.id, type.free)
    if (quantity > available) {
      return validationError({ quantity: [`Only ${available} available for this period.`] })
    }

    const reservation = saveReservation(event.reference, {
      equipment_type_id: type.id,
      equipment_type_name: type.name,
      quantity,
      ...MOCK_EVENT_PERIOD,
      reserved_by: caller.full_name,
      created_at: MOCK_EVENT_PERIOD.starts_at,
      preparation_status: 'not_started',
      preparation_notes: null,
    })
    return HttpResponse.json(asShown(reservation), { status: 201 })
  }),

  http.get(`${EVENT_PATH}/reassessments`, ({ request, params }) => {
    const caller = callerOrRefusal(request, EQUIPMENT_READER_ROLES)
    if (caller instanceof Response) {
      return caller
    }
    const event = eventForReader(caller, String(params.reference))
    if (event === undefined) {
      return eventNotFound()
    }
    return HttpResponse.json(reassessmentsWithConfirmable(event.reference))
  }),

  // Technical Support only. The backend's order: the path, the event, whether it will still run,
  // something marked, the line's outcome, then what is free for the period now (SCRUM-60 AC3).
  http.post(`${EVENT_PATH}/reassessments/:equipmentTypeId/confirm`, ({ request, params }) => {
    const equipmentTypeId = idFromPath(params.equipmentTypeId)
    if (equipmentTypeId === null) {
      return routeNotFound()
    }
    const caller = callerOrRefusal(request, [ROLE.TECHNICAL_SUPPORT_STAFF])
    if (caller instanceof Response) {
      return caller
    }
    const event = eventForStaff(String(params.reference))
    if (event === undefined) {
      return eventNotFound()
    }
    if (EQUIPMENT_NOT_NEEDED_STATUSES.includes(event.status)) {
      return errorResponse(409, 'equipment_not_reservable', RESERVATIONS_CLOSED_MESSAGE)
    }
    const reassessment = reassessmentsOf(event.reference).find(
      (row) => row.equipment_type_id === equipmentTypeId,
    )
    if (reassessment === undefined) {
      return errorResponse(404, 'not_found', NOTHING_TO_REASSESS_MESSAGE)
    }
    const provided = quantityToConfirm(event.reference, reassessment)
    if (provided === null) {
      return errorResponse(409, 'conflict', RECORD_THE_OUTCOME_MESSAGE)
    }
    const cannotMove = refusalToSettle(event.reference, equipmentTypeId, provided)
    if (cannotMove !== undefined) {
      return errorResponse(409, 'reservation_cannot_move', cannotMove)
    }

    settleReassessment(event.reference, equipmentTypeId, provided)
    withdrawSafetyApproval(event.reference)
    const confirmed = reservationsOfEvent(event.reference).filter(
      (reservation) => reservation.equipment_type_id === equipmentTypeId,
    )
    return HttpResponse.json(confirmed.map(asShown))
  }),

  // The backend's order: the body, then the reservation, then the event's safety approval.
  http.put(
    '/api/equipment/reservations/:reservationId/preparation',
    async ({ request, params }) => {
      const caller = callerOrRefusal(request, [ROLE.TECHNICAL_SUPPORT_STAFF])
      if (caller instanceof Response) {
        return caller
      }
      const body = await readBody(request)
      const errors = preparationErrors(body)
      if (Object.keys(errors).length > 0) {
        return validationError(errors)
      }
      const reservation = reservationWithId(Number(params.reservationId))
      if (reservation === undefined) {
        return errorResponse(404, 'not_found', 'Equipment reservation not found.')
      }
      if (!hasSafetyApproval(eventOfReservation(reservation))) {
        return errorResponse(409, 'conflict', PREPARATION_NEEDS_SAFETY_APPROVAL_MESSAGE)
      }

      // preparationErrors has just checked the status is one of the three.
      reservation.preparation_status = body.status as PreparationStatus
      reservation.preparation_notes = savedNotes(body)
      return HttpResponse.json(asShown(reservation))
    },
  ),

  ...equipmentLineHandlers,
]
