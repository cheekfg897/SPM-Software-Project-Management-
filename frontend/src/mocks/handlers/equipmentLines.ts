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

import {
  callerOrRefusal,
  EQUIPMENT_NOT_NEEDED_STATUSES,
  eventForReader,
  eventForStaff,
  eventNotFound,
  withdrawSafetyApproval,
} from './equipmentAccess'
import { mockCatalogueType } from './equipmentCatalogue'
import {
  MOCK_EQUIPMENT_LINES,
  MOCK_EQUIPMENT_TYPES,
  MOCK_EVENT_SCHEDULE,
  MOCK_OUTCOME_RECORDED_AT,
} from './equipmentFixtures'
import type { MockEquipmentLine, MockEquipmentLineStatus, MockEvent } from './equipmentFixtures'
import {
  hasReservationsToReassess,
  markReservationsOfType,
  refusalToSettle,
  settleReassessment,
} from './equipmentReservations'
import {
  EQUIPMENT_TYPE_ID_RANGE_MESSAGE,
  MISSING_MESSAGE,
  positiveWholeNumberError,
  QUANTITY_RANGE_MESSAGE,
  wholeNumberError,
} from './equipmentValidation'
import { AWAITING_DECISION_STATUSES, CHANGES_BEFORE_APPROVAL } from './eventReviewRules'

/**
 * Each event's equipment lines (SCRUM-37), as backend/app/modules/events/routes.py answers them
 * (ADR-0019, ADR-0028), and Technical Support's outcome on each (SCRUM-48, ADR-0040): kept in
 * memory in the order they were added, until resetMockEquipmentLines. The equipment mock reads
 * them for availability's "requested".
 */

const LINES_PATH = '/api/events/requests/:reference/equipment'
const LINE_PATH = `${LINES_PATH}/:lineId`
const OUTCOME_PATH = `${LINE_PATH}/outcome`

/** Only the event's assigned coordinator changes its lines; which event is the lookup's job. */
const LINE_WRITER_ROLES: readonly Role[] = [ROLE.EVENT_COORDINATOR]
/** Only Technical Support record an outcome, on any event's line that will still run (SCRUM-48). */
const OUTCOME_RECORDER_ROLES: readonly Role[] = [ROLE.TECHNICAL_SUPPORT_STAFF]
/**
 * While an event's equipment may change: once the request is approved, until the event is
 * confirmed (EQUIPMENT_EDITABLE_STATUSES, SCRUM-110 AC3).
 */
const EDITABLE_STATUSES: readonly EventRequestStatus[] = [
  EVENT_REQUEST_STATUS.APPROVED,
  EVENT_REQUEST_STATUS.SAFETY_REVIEW,
]
const NOT_YET_APPROVED_MESSAGE = `Equipment can only be added, changed or removed once the event request is approved. ${CHANGES_BEFORE_APPROVAL}`
const NOT_EDITABLE_MESSAGE =
  'Equipment can only be changed before the event is confirmed, and not once it is rejected or cancelled.'
/** The fields a line body may carry (EditEquipmentLineSchema); adding needs the first two. */
const LINE_FIELDS: readonly string[] = ['equipment_type_id', 'quantity', 'notes']
const REQUIRED_TO_ADD: readonly string[] = ['equipment_type_id', 'quantity']
/** The fields an outcome body may carry (RecordEquipmentOutcomeSchema). */
const OUTCOME_FIELDS: readonly string[] = ['provided_quantity', 'note']
const PROVIDED_RANGE_MESSAGE = 'Must be greater than or equal to 0.'
const PROVIDED_ABOVE_REQUESTED_MESSAGE = 'Cannot provide more than was requested.'
const OUTCOME_NOTE_REQUIRED_MESSAGE = 'A note is required unless the whole request can be provided.'
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

/**
 * The name the catalogue has now for an equipment type, or "Equipment type N" for one it doesn't
 * hold (ADR-0061). Shared by the staff record (ADR-0095) and the organiser's lines (ADR-0098).
 */
function equipmentTypeName(equipmentTypeId: number): string {
  const type = mockCatalogueType(equipmentTypeId)
  return type?.name ?? `Equipment type ${String(equipmentTypeId)}`
}

/** The event's line of the type, or undefined: one line per type (ADR-0019). */
export function lineOfType(
  reference: string,
  equipmentTypeId: number,
): MockEquipmentLine | undefined {
  return linesOfEvent(reference).find(
    (candidate) => candidate.equipment_type_id === equipmentTypeId,
  )
}

/** How many units of the type the event asks for: its line's quantity, or 0 without one. */
export function requestedQuantity(reference: string, equipmentTypeId: number): number {
  const line = lineOfType(reference, equipmentTypeId)
  return line === undefined ? 0 : line.quantity
}

/** A line as adding or changing it answers (EquipmentLineSchema). */
function savedLine(line: MockEquipmentLine) {
  const { id, equipment_type_id, quantity, notes, status } = line
  return { id, equipment_type_id, quantity, notes, status }
}

/** How many fewer units are provided than asked for, or null until it is reviewed. */
export function shortfallOf(line: {
  quantity: number
  provided_quantity: number | null
}): number | null {
  return line.provided_quantity === null ? null : line.quantity - line.provided_quantity
}

/**
 * A line in full, as the organiser's record shows it (RecordEquipmentLineSchema, ADR-0104): the
 * type by name, the technical notes, the outcome with the quantity provided and the shortfall,
 * the outcome note and who reviewed it when.
 */
function recordLine(line: MockEquipmentLine) {
  return {
    equipment_type_name: equipmentTypeName(line.equipment_type_id),
    quantity: line.quantity,
    notes: line.notes,
    status: line.status,
    provided_quantity: line.provided_quantity,
    shortfall: shortfallOf(line),
    outcome_note: line.outcome_note,
    reviewed_by: line.reviewed_by,
    reviewed_at: line.reviewed_at,
  }
}

/**
 * The event's lines in the order added, as the read-only staff record shows them: each in full,
 * with Technical Support's outcome and who reviewed it (SCRUM-48 AC5, ADR-0105).
 */
export function equipmentLinesForRecord(reference: string) {
  return linesOfEvent(reference).map(recordLine)
}

/**
 * The event's lines as its record shows them: everything on each to the organiser (SCRUM-37 AC5,
 * SCRUM-48 AC5, ADR-0104), and the line as staff save it to the coordinator (ADR-0098).
 */
export function recordLinesOf(reference: string, viewerRole: Role) {
  const eventLines = linesOfEvent(reference)
  if (viewerRole === ROLE.EVENT_ORGANISER) {
    return eventLines.map(recordLine)
  }
  return eventLines.map(savedLine)
}

/** A line as the event's list shows it to staff, with its shortfall (EquipmentLineWithOutcomeSchema). */
function shownLine(line: MockEquipmentLine) {
  return {
    ...savedLine(line),
    provided_quantity: line.provided_quantity,
    shortfall: shortfallOf(line),
    outcome_note: line.outcome_note,
    reviewed_by: line.reviewed_by,
    reviewed_at: line.reviewed_at,
  }
}

/**
 * The event as its lines come with it (EQUIPMENT_LINES_EVENT_FIELDS): when it is, and its status
 * (SCRUM-110). Every mock event shares one period.
 */
function eventShown(event: MockEvent) {
  return {
    reference: event.reference,
    name: event.name,
    ...MOCK_EVENT_SCHEDULE,
    status: event.status,
  }
}

/** The decoded JSON body, or undefined for anything that is not a JSON object. */
async function objectBody(request: Request): Promise<Record<string, unknown> | undefined> {
  const body: unknown = await request.json().catch(() => undefined)
  return isRecord(body) ? body : undefined
}

function notAnObject() {
  return errorResponse(400, 'validation_error', 'Request body must be a JSON object.')
}

/** "Unknown field." for each field of the body that is not one of `known`. */
function unknownFieldErrors(body: Record<string, unknown>, known: readonly string[]): FieldErrors {
  const errors: FieldErrors = {}
  for (const name of Object.keys(body)) {
    if (!known.includes(name)) {
      errors[name] = ['Unknown field.']
    }
  }
  return errors
}

/** Whether an optional text field holds text, null, or nothing at all. */
function isOptionalText(value: unknown): boolean {
  return value === undefined || value === null || typeof value === 'string'
}

/** Problems with a line body, by field, in the backend's wording. `required` must be sent. */
function lineErrors(body: Record<string, unknown>, required: readonly string[]): FieldErrors {
  const errors = unknownFieldErrors(body, LINE_FIELDS)
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
  if (!isOptionalText(body.notes)) {
    errors.notes = ['Not a valid string.']
  }
  return errors
}

/** Problems with an outcome body, by field, in the backend's wording. */
function outcomeErrors(body: Record<string, unknown>): FieldErrors {
  const errors = unknownFieldErrors(body, OUTCOME_FIELDS)
  const provided = body.provided_quantity
  const providedError =
    provided === undefined ? MISSING_MESSAGE : wholeNumberError(provided, 0, PROVIDED_RANGE_MESSAGE)
  if (providedError !== undefined) {
    errors.provided_quantity = [providedError]
  }
  if (!isOptionalText(body.note)) {
    errors.note = ['Not a valid string.']
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
 * The coordinator's own event, if its equipment may change now, or the refusal: another's, an
 * unassigned one or a draft is a 404; one not approved yet, or past the edit window, a 409.
 */
function editableEventOrRefusal(caller: MockAccount, reference: string): MockEvent | Response {
  const event = eventForReader(caller, reference)
  if (event === undefined) {
    return eventNotFound()
  }
  if (AWAITING_DECISION_STATUSES.includes(event.status)) {
    return errorResponse(409, 'equipment_not_editable', NOT_YET_APPROVED_MESSAGE)
  }
  if (!EDITABLE_STATUSES.includes(event.status)) {
    return errorResponse(409, 'equipment_not_editable', NOT_EDITABLE_MESSAGE)
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

/** Whether `changed` asks for another equipment type or quantity than `line` (`_changes_the_equipment`). */
function asksForNewEquipment(line: MockEquipmentLine, changed: MockEquipmentLine): boolean {
  return changed.equipment_type_id !== line.equipment_type_id || changed.quantity !== line.quantity
}

/** The line with no outcome, awaiting Technical Support's review again (`_clear_outcome`). */
function withoutOutcome(line: MockEquipmentLine): MockEquipmentLine {
  return {
    ...line,
    status: 'requested',
    provided_quantity: null,
    outcome_note: null,
    reviewed_by: null,
    reviewed_at: null,
  }
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

/** Which outcome `provided` units of `quantity` is (`outcome_status_for`). */
function outcomeStatus(quantity: number, provided: number): MockEquipmentLineStatus {
  if (provided === quantity) {
    return 'fulfilled'
  }
  if (provided === 0) {
    return 'unavailable'
  }
  return 'partially_fulfilled'
}

/** More than was asked for, or a shortfall with no note, refused (`_check_outcome_is_possible`). */
function outcomeRefusal(line: MockEquipmentLine, provided: number, note: string | null) {
  if (provided > line.quantity) {
    return validationError({ provided_quantity: [PROVIDED_ABOVE_REQUESTED_MESSAGE] })
  }
  if (provided < line.quantity && note === null) {
    return validationError({ note: [OUTCOME_NOTE_REQUIRED_MESSAGE] })
  }
  return undefined
}

/** An outcome on an event that won't run, refused naming its status (SCRUM-48 AC8). */
function outcomesClosed(event: MockEvent) {
  return errorResponse(
    409,
    'conflict',
    `An equipment outcome can't be recorded for an event that is completed, cancelled or rejected; this one is ${event.status}.`,
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

  // The body, the event, whether it is editable, the line, the type, then a duplicate. Only the
  // fields sent change, and a new type or quantity reopens the line for review (SCRUM-37 AC4).
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

    const asksForNew = asksForNewEquipment(line, changed)
    // A new quantity on the same type marks its reservations for reassessment (SCRUM-60 AC8).
    if (asksForNew && changed.equipment_type_id === line.equipment_type_id) {
      markReservationsOfType(event.reference, line.equipment_type_id)
    }
    Object.assign(line, asksForNew ? withoutOutcome(changed) : changed)
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

  // Technical Support only. The body, the event, whether it will still run, the line, what the
  // line asked for, then what its marked reservations can keep. Every call overwrites the outcome,
  // so a revision is recording again (SCRUM-48 AC6), and it withdraws a safety approval (AC7). It
  // settles the line's marked reservations, which also withdraws one (SCRUM-60 AC4, AC10).
  http.post(OUTCOME_PATH, async ({ request, params }) => {
    const caller = callerOrRefusal(request, OUTCOME_RECORDER_ROLES)
    if (caller instanceof Response) {
      return caller
    }
    const body = await objectBody(request)
    if (body === undefined) {
      return notAnObject()
    }
    const errors = outcomeErrors(body)
    if (Object.keys(errors).length > 0) {
      return validationError(errors)
    }
    const event = eventForStaff(String(params.reference))
    if (event === undefined) {
      return eventNotFound()
    }
    if (EQUIPMENT_NOT_NEEDED_STATUSES.includes(event.status)) {
      return outcomesClosed(event)
    }
    const line = lineOfEvent(event, String(params.lineId))
    if (line === undefined) {
      return lineNotFound()
    }
    const provided = Number(body.provided_quantity)
    const note = storedNotes(body.note)
    const refused = outcomeRefusal(line, provided, note)
    if (refused !== undefined) {
      return refused
    }
    const cannotMove = refusalToSettle(event.reference, line.equipment_type_id, provided)
    if (cannotMove !== undefined) {
      return errorResponse(409, 'reservation_cannot_move', cannotMove)
    }

    const isRevision = line.provided_quantity !== null
    const status = outcomeStatus(line.quantity, provided)
    line.status = status
    line.provided_quantity = provided
    // The note is replaced, not merged: a revision sent with no note clears the old one.
    line.outcome_note = note
    line.reviewed_by = caller.full_name
    line.reviewed_at = MOCK_OUTCOME_RECORDED_AT
    // A revision withdraws the event's safety approval (AC7); this mock's event in Safety Review
    // is still waiting for the Safety Officer, so it has none to lose.
    if (isRevision) {
      withdrawSafetyApproval(event.reference)
    }
    if (hasReservationsToReassess(event.reference, line.equipment_type_id)) {
      settleReassessment(event.reference, line.equipment_type_id, provided)
      withdrawSafetyApproval(event.reference)
    }
    return HttpResponse.json(shownLine(line))
  }),
]
