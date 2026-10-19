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
  resetMockEquipmentEvents,
} from './equipmentAccess'
import {
  MOCK_EQUIPMENT_TYPES,
  MOCK_EVENT_PERIOD,
  MOCK_SAFETY_APPROVED_EVENT_REFERENCES,
} from './equipmentFixtures'
import type { MockEquipmentType } from './equipmentFixtures'
import { equipmentLineHandlers, requestedQuantity, resetMockEquipmentLines } from './equipmentLines'
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
 * lines (SCRUM-37, equipmentLines.ts). The catalogue's types are answered in
 * equipmentCatalogue.ts. Reservations live in memory until resetMockEquipment.
 */

const EVENT_PATH = '/api/equipment/events/:reference'

interface MockReservation {
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

/** Forget every reservation and line change made since the mock started. Runs after every test. */
export function resetMockEquipment(): void {
  reservations = []
  reservationEvents = new Map()
  resetMockEquipmentLines()
  resetMockEquipmentEvents()
}

/** Every equipment type, by name, as the backend lists the catalogue. */
function equipmentTypesByName(): MockEquipmentType[] {
  return [...MOCK_EQUIPMENT_TYPES].sort((first, second) => first.name.localeCompare(second.name))
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

function availableQuantity(equipmentTypeId: number, free: number): number {
  return Math.max(free - reservedQuantity(equipmentTypeId), 0)
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
    if (eventForReader(caller, String(params.reference)) === undefined) {
      return eventNotFound()
    }
    return HttpResponse.json(reservations)
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
      return errorResponse(
        409,
        'equipment_not_reservable',
        "Equipment can't be reserved for an event that is completed, cancelled or rejected.",
      )
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
    const available = availableQuantity(type.id, type.free)
    if (quantity > available) {
      return validationError({ quantity: [`Only ${available} available for this period.`] })
    }

    const reservation: MockReservation = {
      id: reservations.length + 1,
      equipment_type_id: type.id,
      equipment_type_name: type.name,
      quantity,
      ...MOCK_EVENT_PERIOD,
      reserved_by: caller.full_name,
      created_at: MOCK_EVENT_PERIOD.starts_at,
      preparation_status: 'not_started',
      preparation_notes: null,
    }
    reservations.push(reservation)
    reservationEvents.set(reservation.id, event.reference)
    return HttpResponse.json(reservation, { status: 201 })
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
      const reservation = reservations.find((saved) => saved.id === Number(params.reservationId))
      if (reservation === undefined) {
        return errorResponse(404, 'not_found', 'Equipment reservation not found.')
      }
      const eventReference = reservationEvents.get(reservation.id) ?? ''
      if (!MOCK_SAFETY_APPROVED_EVENT_REFERENCES.includes(eventReference)) {
        return errorResponse(409, 'conflict', PREPARATION_NEEDS_SAFETY_APPROVAL_MESSAGE)
      }

      // preparationErrors has just checked the status is one of the three.
      reservation.preparation_status = body.status as PreparationStatus
      reservation.preparation_notes = savedNotes(body)
      return HttpResponse.json(reservation)
    },
  ),

  ...equipmentLineHandlers,
]
