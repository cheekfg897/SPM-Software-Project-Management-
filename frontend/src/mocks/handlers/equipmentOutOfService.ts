import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'

import { ROLE } from '@/config/roles'
import type { FieldErrors } from '@/lib/api'
import { isRecord } from '@/lib/isRecord'

import { errorResponse, validationError } from '../responses'

import { callerOrRefusal, withdrawSafetyApproval } from './equipmentAccess'
import { idFromPath, mockCatalogueType, routeNotFound } from './equipmentCatalogue'
import { MOCK_BACK_IN_SERVICE_AT, MOCK_OUT_OF_SERVICE_RECORDED_AT } from './equipmentFixtures'
import {
  addOutOfServiceEntry,
  entriesStillOut,
  outOfServiceEntry,
  outOfServiceQuantity,
} from './equipmentOutOfServiceEntries'
import { eventsReservingType, isTypeShort } from './equipmentReservations'
import {
  MISSING_MESSAGE,
  positiveWholeNumberError,
  QUANTITY_RANGE_MESSAGE,
} from './equipmentValidation'

/**
 * Taking units of an equipment type out of service and putting them back (SCRUM-47, ADR-0046),
 * as backend/app/modules/equipment/routes.py answers it: Technical Support only, the body checked
 * as MarkOutOfServiceSchema checks it, then the type, then how many are in service. An event whose
 * reservation this leaves short loses its safety approval (AC5). The entries are kept in
 * equipmentOutOfServiceEntries.ts. The coordinator's notice (AC3) is not sent: the notifications
 * mock keeps its own list.
 */

const REASONS = ['damaged', 'under_maintenance']
const UNKNOWN_REASON_MESSAGE = 'Must be one of: damaged, under_maintenance.'
const FIELDS = ['quantity', 'reason']
const TECHNICAL_SUPPORT_ONLY = [ROLE.TECHNICAL_SUPPORT_STAFF]

function reasonError(value: unknown): string | undefined {
  if (value === null) {
    return 'Field may not be null.'
  }
  return typeof value === 'string' && REASONS.includes(value) ? undefined : UNKNOWN_REASON_MESSAGE
}

/** Each field's problems, in marshmallow's words: unknown, missing or wrong. */
function bodyErrors(body: Record<string, unknown>): FieldErrors {
  const errors: FieldErrors = {}
  for (const field of Object.keys(body)) {
    if (!FIELDS.includes(field)) {
      errors[field] = ['Unknown field.']
    }
  }
  const checks = {
    quantity: positiveWholeNumberError(body.quantity, QUANTITY_RANGE_MESSAGE),
    reason: reasonError(body.reason),
  }
  for (const [field, error] of Object.entries(checks)) {
    const message = body[field] === undefined ? MISSING_MESSAGE : error
    if (message !== undefined) {
      errors[field] = [message]
    }
  }
  return errors
}

/** The backend's 400 for more units than are in service: its message is the field's message. */
function tooManyUnits(inService: number) {
  const message = `Only ${inService} units are in service.`
  return HttpResponse.json(
    { error: 'validation_error', message, details: { quantity: [message] } },
    { status: 400 },
  )
}

/**
 * Every event with a reservation of the type loses its safety approval (AC5). The backend
 * withdraws it for each newly flagged reservation, and here every reservation of a type is
 * flagged together (equipment.ts).
 */
function withdrawApprovalsOfEventsReserving(equipmentTypeId: number): void {
  for (const reference of eventsReservingType(equipmentTypeId)) {
    withdrawSafetyApproval(reference)
  }
}

function typeNotFound() {
  return errorResponse(404, 'not_found', 'Equipment type not found.')
}

export const equipmentOutOfServiceHandlers: RequestHandler[] = [
  http.post('/api/equipment/types/:equipmentTypeId/out-of-service', async ({ request, params }) => {
    const typeId = idFromPath(params.equipmentTypeId)
    if (typeId === null) {
      return routeNotFound()
    }
    const caller = callerOrRefusal(request, TECHNICAL_SUPPORT_ONLY)
    if (caller instanceof Response) {
      return caller
    }
    const body: unknown = await request.json().catch(() => null)
    if (!isRecord(body)) {
      return errorResponse(400, 'validation_error', 'Request body must be a JSON object.')
    }
    const errors = bodyErrors(body)
    if (Object.keys(errors).length > 0) {
      return validationError(errors)
    }
    const type = mockCatalogueType(typeId)
    if (type === undefined) {
      return typeNotFound()
    }
    // bodyErrors has just checked it is a whole number.
    const quantity = body.quantity as number
    const inService = type.total_quantity - outOfServiceQuantity(type.id)
    if (quantity > inService) {
      return tooManyUnits(inService)
    }

    const wasShort = isTypeShort(type.id)
    const entry = addOutOfServiceEntry({
      equipment_type_id: type.id,
      quantity,
      reason: String(body.reason),
      recorded_by: caller.full_name,
      recorded_at: MOCK_OUT_OF_SERVICE_RECORDED_AT,
      resolved_by: null,
      resolved_at: null,
    })
    if (!wasShort && isTypeShort(type.id)) {
      withdrawApprovalsOfEventsReserving(type.id)
    }
    return HttpResponse.json(entry, { status: 201 })
  }),

  http.get('/api/equipment/types/:equipmentTypeId/out-of-service', ({ request, params }) => {
    const typeId = idFromPath(params.equipmentTypeId)
    if (typeId === null) {
      return routeNotFound()
    }
    const caller = callerOrRefusal(request, TECHNICAL_SUPPORT_ONLY)
    if (caller instanceof Response) {
      return caller
    }
    if (mockCatalogueType(typeId) === undefined) {
      return typeNotFound()
    }
    return HttpResponse.json(entriesStillOut(typeId))
  }),

  http.post('/api/equipment/out-of-service/:entryId/return', ({ request, params }) => {
    const entryId = idFromPath(params.entryId)
    if (entryId === null) {
      return routeNotFound()
    }
    const caller = callerOrRefusal(request, TECHNICAL_SUPPORT_ONLY)
    if (caller instanceof Response) {
      return caller
    }
    const entry = outOfServiceEntry(entryId)
    if (entry === undefined) {
      return errorResponse(404, 'not_found', 'Out-of-service entry not found.')
    }
    if (entry.resolved_at !== null) {
      return errorResponse(409, 'conflict', 'These units are already back in service.')
    }
    entry.resolved_by = caller.full_name
    entry.resolved_at = MOCK_BACK_IN_SERVICE_AT
    return HttpResponse.json(entry)
  }),
]
