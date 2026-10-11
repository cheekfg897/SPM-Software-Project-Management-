import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'

import { EQUIPMENT_READER_ROLES, ROLE } from '@/config/roles'
import type { Role } from '@/config/roles'
import { isRecord } from '@/lib/isRecord'

import type { MockAccount } from '../fixtures/accounts'
import { errorResponse, INVALID_TOKEN_MESSAGE, validationError } from '../responses'

import { accountForRequest } from './auth'
import { MOCK_EQUIPMENT_TYPES, MOCK_EVENT_PERIOD, MOCK_EVENT_REFERENCES } from './equipmentFixtures'

/**
 * The equipment endpoints, as backend/app/modules/equipment/routes.py answers them (SCRUM-45
 * availability, SCRUM-46 reservations). Reservations live in memory until resetMockEquipment.
 */

const EVENT_PATH = '/api/equipment/events/:reference'
const MISSING_MESSAGE = 'Missing data for required field.'

interface MockReservation {
  id: number
  equipment_type_id: number
  equipment_type_name: string
  quantity: number
  starts_at: string
  ends_at: string
  reserved_by: string
  created_at: string
}

let reservations: MockReservation[] = []

/** Forget every reservation made since the mock started. Runs after every test. */
export function resetMockEquipment(): void {
  reservations = []
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

function availabilityRows() {
  return MOCK_EQUIPMENT_TYPES.map((type) => {
    const available = availableQuantity(type.id, type.free)
    return {
      equipment_type_id: type.id,
      equipment_type_name: type.name,
      available,
      requested: type.requested,
      shortfall: Math.max(type.requested - available, 0),
    }
  })
}

/** The caller, or the refusal for a missing token or a role that may not call this. */
function callerOrRefusal(request: Request, allowedRoles: readonly Role[]) {
  const user = accountForRequest(request)
  if (user === undefined) {
    return errorResponse(401, 'authentication_error', INVALID_TOKEN_MESSAGE)
  }
  if (!allowedRoles.includes(user.role)) {
    return errorResponse(
      403,
      'authorization_error',
      'You do not have permission to perform this action.',
    )
  }
  return user
}

function eventNotFound() {
  return errorResponse(404, 'not_found', 'Event request not found.')
}

/**
 * Whether the reader may see the event's equipment: Technical Support any event's, a coordinator
 * only one assigned to them. Anything else is the same 404 as an unknown event (ADR-0019).
 */
function mayRead(reader: MockAccount, reference: string): boolean {
  const event = MOCK_EVENT_REFERENCES[reference]
  if (event === undefined) {
    return false
  }
  return reader.role === ROLE.TECHNICAL_SUPPORT_STAFF || event.coordinator_id === reader.id
}

/** Problems with the reservation body, by field, in the backend's wording (EquipmentUnitsSchema). */
function bodyErrors(body: unknown): Record<string, string[]> {
  const sent = isRecord(body) ? body : {}
  const errors: Record<string, string[]> = {}
  for (const name of ['equipment_type_id', 'quantity']) {
    if (sent[name] === undefined) {
      errors[name] = [MISSING_MESSAGE]
    } else if (!Number.isInteger(sent[name])) {
      errors[name] = ['Not a valid integer.']
    }
  }
  if (errors.equipment_type_id === undefined && Number(sent.equipment_type_id) < 1) {
    errors.equipment_type_id = ['equipment_type_id must be a positive number.']
  }
  if (errors.quantity === undefined && Number(sent.quantity) < 1) {
    errors.quantity = ['Quantity must be at least 1.']
  }
  return errors
}

export const equipmentHandlers: RequestHandler[] = [
  http.get(`${EVENT_PATH}/availability`, ({ request, params }) => {
    const caller = callerOrRefusal(request, EQUIPMENT_READER_ROLES)
    if (caller instanceof Response) {
      return caller
    }
    if (!mayRead(caller, String(params.reference))) {
      return eventNotFound()
    }
    return HttpResponse.json(availabilityRows())
  }),

  http.get(`${EVENT_PATH}/reservations`, ({ request, params }) => {
    const caller = callerOrRefusal(request, EQUIPMENT_READER_ROLES)
    if (caller instanceof Response) {
      return caller
    }
    if (!mayRead(caller, String(params.reference))) {
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
    const event = MOCK_EVENT_REFERENCES[String(params.reference)]
    if (event === undefined) {
      return eventNotFound()
    }
    if (!event.accepts_reservations) {
      return errorResponse(
        409,
        'equipment_not_reservable',
        "Equipment can't be reserved for an event that is completed, cancelled or rejected.",
      )
    }

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
    }
    reservations.push(reservation)
    return HttpResponse.json(reservation, { status: 201 })
  }),
]
