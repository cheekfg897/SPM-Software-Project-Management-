import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'

import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import type { EventRequestStatus } from '@/config/eventStatus'
import { EQUIPMENT_READER_ROLES, ROLE } from '@/config/roles'
import type { Role } from '@/config/roles'
import type { FieldErrors } from '@/lib/api'
import { isRecord } from '@/lib/isRecord'

import type { MockAccount } from '../fixtures/accounts'
import { errorResponse, validationError } from '../responses'

import { callerOrRefusal, eventForReader, eventNotFound } from './equipmentAccess'
import {
  MOCK_EQUIPMENT_LINES,
  MOCK_EQUIPMENT_TYPES,
  MOCK_EVENT_SCHEDULE,
} from './equipmentFixtures'
import type { MockEquipmentLine, MockEvent } from './equipmentFixtures'
import {
  EQUIPMENT_TYPE_ID_RANGE_MESSAGE,
  MISSING_MESSAGE,
  positiveWholeNumberError,
  QUANTITY_RANGE_MESSAGE,
} from './equipmentValidation'

/**
 * Each event's equipment lines (SCRUM-37), as backend/app/modules/events/routes.py answers them
 * (ADR-0019, ADR-0028): kept in memory in the order they were added, until
 * resetMockEquipmentLines. The equipment mock reads them for availability's "requested".
 */

const LINES_PATH = '/api/events/requests/:reference/equipment'
const LINE_PATH = `${LINES_PATH}/:lineId`

/** Only the event's assigned coordinator changes its lines; which event is the lookup's job. */
const LINE_WRITER_ROLES: readonly Role[] = [ROLE.EVENT_COORDINATOR]
/** While an event's equipment may change (EQUIPMENT_EDITABLE_STATUSES). */
const EDITABLE_STATUSES: readonly EventRequestStatus[] = [
  EVENT_REQUEST_STATUS.SUBMITTED,
  EVENT_REQUEST_STATUS.UNDER_REVIEW,
  EVENT_REQUEST_STATUS.APPROVED,
]
/** The fields a line body may carry (EditEquipmentLineSchema); adding needs the first two. */
const LINE_FIELDS: readonly string[] = ['equipment_type_id', 'quantity', 'notes']
const REQUIRED_TO_ADD: readonly string[] = ['equipment_type_id', 'quantity']
const RANGE_MESSAGES = {
  equipment_type_id: EQUIPMENT_TYPE_ID_RANGE_MESSAGE,
  quantity: QUANTITY_RANGE_MESSAGE,
}
/** Ids for lines added through the mock: past every seeded one, never reused. */
const FIRST_ADDED_LINE_ID = 100

let lines: MockEquipmentLine[] = []
let nextLineId = FIRST_ADDED_LINE_ID

/** Put every event's lines back as they started. Runs after every test. */
export function resetMockEquipmentLines(): void {
  lines = MOCK_EQUIPMENT_LINES.map((line) => ({ ...line }))
  nextLineId = FIRST_ADDED_LINE_ID
}

resetMockEquipmentLines()

/** The event's lines, in the order they were added. */
function linesOfEvent(reference: string): MockEquipmentLine[] {
  return lines.filter((line) => line.event_reference === reference)
}

/** How many units of the type the event asks for: its line's quantity, or 0 without one. */
export function requestedQuantity(reference: string, equipmentTypeId: number): number {
  const line = linesOfEvent(reference).find(
    (candidate) => candidate.equipment_type_id === equipmentTypeId,
  )
  return line === undefined ? 0 : line.quantity
}

/** A line as adding or changing it answers (EquipmentLineSchema). */
function savedLine(line: MockEquipmentLine) {
  const { id, equipment_type_id, quantity, notes, status } = line
  return { id, equipment_type_id, quantity, notes, status }
}

/** A line as the event's list shows it to staff, with its shortfall (EquipmentLineWithOutcomeSchema). */
function shownLine(line: MockEquipmentLine) {
  const shortfall = line.provided_quantity === null ? null : line.quantity - line.provided_quantity
  return {
    ...savedLine(line),
    provided_quantity: line.provided_quantity,
    shortfall,
    outcome_note: line.outcome_note,
    reviewed_by: line.reviewed_by,
    reviewed_at: line.reviewed_at,
  }
}

/** The event as the list describes it (EQUIPMENT_EVENT_FIELDS). Every mock event shares one period. */
function eventShown(event: MockEvent) {
  return { reference: event.reference, name: event.name, ...MOCK_EVENT_SCHEDULE }
}

/** The decoded JSON body, or undefined for anything that is not a JSON object. */
async function objectBody(request: Request): Promise<Record<string, unknown> | undefined> {
  const body: unknown = await request.json().catch(() => undefined)
  return isRecord(body) ? body : undefined
}

function notAnObject() {
  return errorResponse(400, 'validation_error', 'Request body must be a JSON object.')
}

/** Problems with a line body, by field, in the backend's wording. `required` must be sent. */
function lineErrors(body: Record<string, unknown>, required: readonly string[]): FieldErrors {
  const errors: FieldErrors = {}
  for (const name of Object.keys(body)) {
    if (!LINE_FIELDS.includes(name)) {
      errors[name] = ['Unknown field.']
    }
  }
  for (const name of required) {
    if (body[name] === undefined) {
      errors[name] = [MISSING_MESSAGE]
    }
  }
  for (const [name, rangeMessage] of Object.entries(RANGE_MESSAGES)) {
    const error =
      body[name] === undefined ? undefined : positiveWholeNumberError(body[name], rangeMessage)
    if (error !== undefined) {
      errors[name] = [error]
    }
  }
  const notes = body.notes
  if (notes !== undefined && notes !== null && typeof notes !== 'string') {
    errors.notes = ['Not a valid string.']
  }
  return errors
}

/** Notes as the backend keeps them: trimmed, and none when blank. */
function storedNotes(notes: unknown): string | null {
  if (typeof notes !== 'string') {
    return null
  }
  const trimmed = notes.trim()
  return trimmed === '' ? null : trimmed
}

/**
 * The coordinator's own event, if its equipment may still change, or the refusal: another's,
 * an unassigned one or a draft is a 404, one past the edit window a 409.
 */
function editableEventOrRefusal(caller: MockAccount, reference: string): MockEvent | Response {
  const event = eventForReader(caller, reference)
  if (event === undefined) {
    return eventNotFound()
  }
  if (!EDITABLE_STATUSES.includes(event.status)) {
    return errorResponse(
      409,
      'equipment_not_editable',
      'Equipment can only be changed while the request is submitted, under review or approved.',
    )
  }
  return event
}

/** The event's own line with that id, or undefined. */
function lineOfEvent(event: MockEvent, lineId: string): MockEquipmentLine | undefined {
  return linesOfEvent(event.reference).find((line) => line.id === Number(lineId))
}

function lineNotFound() {
  return errorResponse(404, 'not_found', 'Equipment line not found.')
}

function isKnownType(equipmentTypeId: number): boolean {
  return MOCK_EQUIPMENT_TYPES.some((type) => type.id === equipmentTypeId)
}

function typeNotFound() {
  return validationError({ equipment_type_id: ['Equipment type not found.'] })
}

/** Whether `quantity` is below what Technical Support have said they will provide (SCRUM-48). */
function isBelowOutcome(line: MockEquipmentLine, quantity: number): boolean {
  return line.provided_quantity !== null && quantity < line.provided_quantity
}

function belowOutcome(line: MockEquipmentLine) {
  const provided = String(line.provided_quantity)
  return validationError({
    quantity: [
      `Quantity cannot be below the ${provided} units Technical Support has said they will provide.`,
    ],
  })
}

/** Whether another of the event's lines already has the type (one line per type, ADR-0019). */
function typeTakenByAnotherLine(
  event: MockEvent,
  equipmentTypeId: number,
  lineId: number | null,
): boolean {
  return linesOfEvent(event.reference).some(
    (line) => line.equipment_type_id === equipmentTypeId && line.id !== lineId,
  )
}

function duplicateLine() {
  return errorResponse(
    409,
    'conflict',
    'This event already has a line for that equipment type. Edit that line instead.',
  )
}

export const equipmentLineHandlers: RequestHandler[] = [
  http.get(LINES_PATH, ({ request, params }) => {
    const caller = callerOrRefusal(request, EQUIPMENT_READER_ROLES)
    if (caller instanceof Response) {
      return caller
    }
    const event = eventForReader(caller, String(params.reference))
    if (event === undefined) {
      return eventNotFound()
    }
    return HttpResponse.json({
      event: eventShown(event),
      equipment_lines: linesOfEvent(event.reference).map(shownLine),
    })
  }),

  // The backend's order: the body, the event, whether it is editable, the type, then a duplicate.
  http.post(LINES_PATH, async ({ request, params }) => {
    const caller = callerOrRefusal(request, LINE_WRITER_ROLES)
    if (caller instanceof Response) {
      return caller
    }
    const body = await objectBody(request)
    if (body === undefined) {
      return notAnObject()
    }
    const errors = lineErrors(body, REQUIRED_TO_ADD)
    if (Object.keys(errors).length > 0) {
      return validationError(errors)
    }
    const event = editableEventOrRefusal(caller, String(params.reference))
    if (event instanceof Response) {
      return event
    }
    const equipmentTypeId = Number(body.equipment_type_id)
    if (!isKnownType(equipmentTypeId)) {
      return typeNotFound()
    }
    if (typeTakenByAnotherLine(event, equipmentTypeId, null)) {
      return duplicateLine()
    }

    const line: MockEquipmentLine = {
      id: nextLineId,
      event_reference: event.reference,
      equipment_type_id: equipmentTypeId,
      quantity: Number(body.quantity),
      notes: storedNotes(body.notes),
      status: 'requested',
      provided_quantity: null,
      outcome_note: null,
      reviewed_by: null,
      reviewed_at: null,
    }
    nextLineId += 1
    lines.push(line)
    return HttpResponse.json(savedLine(line), { status: 201 })
  }),

  // The body, the event, whether it is editable, the line, the type, the quantity against what
  // will be provided, then a duplicate. Only the fields sent change.
  http.patch(LINE_PATH, async ({ request, params }) => {
    const caller = callerOrRefusal(request, LINE_WRITER_ROLES)
    if (caller instanceof Response) {
      return caller
    }
    const body = await objectBody(request)
    if (body === undefined) {
      return notAnObject()
    }
    const errors = lineErrors(body, [])
    if (Object.keys(errors).length > 0) {
      return validationError(errors)
    }
    const event = editableEventOrRefusal(caller, String(params.reference))
    if (event instanceof Response) {
      return event
    }
    const line = lineOfEvent(event, String(params.lineId))
    if (line === undefined) {
      return lineNotFound()
    }

    if (body.equipment_type_id !== undefined && !isKnownType(Number(body.equipment_type_id))) {
      return typeNotFound()
    }
    if (body.quantity !== undefined && isBelowOutcome(line, Number(body.quantity))) {
      return belowOutcome(line)
    }
    const changed = { ...line }
    if (body.equipment_type_id !== undefined) {
      changed.equipment_type_id = Number(body.equipment_type_id)
    }
    if (body.quantity !== undefined) {
      changed.quantity = Number(body.quantity)
    }
    if (body.notes !== undefined) {
      changed.notes = storedNotes(body.notes)
    }
    if (typeTakenByAnotherLine(event, changed.equipment_type_id, line.id)) {
      return duplicateLine()
    }

    Object.assign(line, changed)
    return HttpResponse.json(savedLine(line))
  }),

  http.delete(LINE_PATH, ({ request, params }) => {
    const caller = callerOrRefusal(request, LINE_WRITER_ROLES)
    if (caller instanceof Response) {
      return caller
    }
    const event = editableEventOrRefusal(caller, String(params.reference))
    if (event instanceof Response) {
      return event
    }
    const line = lineOfEvent(event, String(params.lineId))
    if (line === undefined) {
      return lineNotFound()
    }
    lines = lines.filter((candidate) => candidate !== line)
    return new HttpResponse(null, { status: 204 })
  }),
]
