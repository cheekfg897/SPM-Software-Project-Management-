import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'

import { INTERNAL_ROLES, ROLE } from '@/config/roles'
import type { Role } from '@/config/roles'
import type { FieldErrors } from '@/lib/api'
import { isRecord } from '@/lib/isRecord'

import { errorResponse, notAllowed, notAuthenticated, validationError } from '../responses'

import { accountForRequest } from './auth'
import { MOCK_CATALOGUE_TYPES, MOCK_VENUE_IDS } from './equipmentCatalogueFixtures'
import type { MockCatalogueType } from './equipmentCatalogueFixtures'

/**
 * The equipment catalogue endpoints (SCRUM-27), as backend/app/modules/equipment answers them:
 * every internal role reads, only Technical Support add and change, and the body is checked as
 * EditEquipmentTypeSchema checks it (ADR-0014). Changes live in memory until the next reset.
 */

const TYPES_PATH = '/api/equipment/types'
const TYPE_PATH = `${TYPES_PATH}/:equipmentTypeId`

export const DUPLICATE_NAME_MESSAGE = 'An equipment type with this name already exists.'
export const NO_LOCATION_MESSAGE = 'Either venue_id or store_name is required.'
export const BOTH_LOCATIONS_MESSAGE = 'Set either venue_id or store_name, not both.'
const NOT_FOUND_MESSAGE = 'Equipment type not found.'
/** Werkzeug's own 404, for a path Flask's `<int:…>` does not match, whoever asks. */
const ROUTE_NOT_FOUND_MESSAGE =
  'The requested URL was not found on the server. If you entered the URL manually please check your spelling and try again.'
const NOT_AN_OBJECT_MESSAGE = 'Request body must be a JSON object.'
const MISSING_MESSAGE = 'Missing data for required field.'
const NOT_NULL_MESSAGE = 'Field may not be null.'
const NOT_A_STRING_MESSAGE = 'Not a valid string.'
const NOT_AN_INTEGER_MESSAGE = 'Not a valid integer.'
const BLANK_MESSAGE = 'Must not be blank.'
const UNKNOWN_FIELD_MESSAGE = 'Unknown field.'
/** NAME_MAX_LENGTH and STORE_NAME_MAX_LENGTH in the equipment models. */
const MAX_TEXT_LENGTH = 200

const EDITOR_ROLES: readonly Role[] = [ROLE.TECHNICAL_SUPPORT_STAFF]
/** Fields a new type must have. An update may leave any of them out. */
const REQUIRED_ON_CREATE = ['name', 'total_quantity']
/** What a new type has for a field left out of its body (the schema's load_default). */
const CREATE_DEFAULTS = { description: null, venue_id: null, store_name: null }
/**
 * A new type before its body is applied. A body that passed the checks has every one of these
 * fields (the defaults fill the rest), so none of these values is ever saved.
 */
const BLANK_TYPE = { name: '', total_quantity: 0, ...CREATE_DEFAULTS }

let types: MockCatalogueType[] = []
let nextId = 0

/** Put the catalogue back as it started, so no test sees a type another test added or changed. */
export function resetMockEquipmentCatalogue(): void {
  types = MOCK_CATALOGUE_TYPES.map((type) => ({ ...type }))
  nextId = MOCK_CATALOGUE_TYPES.length + 1
}
resetMockEquipmentCatalogue()

/** The 401 or 403 the backend's decorators send, or null when the caller's role may do this. */
function refusalFor(request: Request, allowedRoles: readonly Role[]) {
  const caller = accountForRequest(request)
  if (caller === undefined) {
    return notAuthenticated()
  }
  if (!allowedRoles.includes(caller.role)) {
    return notAllowed()
  }
  return null
}

/** The id in the path, or null when Flask's `<int:…>` would not match it. */
function idFromPath(param: unknown): number | null {
  const text = String(param)
  return /^\d+$/.test(text) ? Number(text) : null
}

function routeNotFound() {
  return errorResponse(404, 'not_found', ROUTE_NOT_FOUND_MESSAGE)
}

function typeNotFound() {
  return errorResponse(404, 'not_found', NOT_FOUND_MESSAGE)
}

function isWholeNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value)
}

function isSet(value: unknown): boolean {
  return value !== undefined && value !== null
}

/** A text field's problems: not a string, blank, or longer than the column. */
function textErrors(value: unknown, label: string): string[] {
  if (typeof value !== 'string') {
    return [NOT_A_STRING_MESSAGE]
  }
  const errors: string[] = []
  if (value.trim() === '') {
    errors.push(BLANK_MESSAGE)
  }
  // Python counts characters, not UTF-16 units.
  if ([...value].length > MAX_TEXT_LENGTH) {
    errors.push(`${label} must be at most ${MAX_TEXT_LENGTH} characters.`)
  }
  return errors
}

/** Each field's problems with the value sent, as marshmallow words them; [] when there are none. */
const FIELD_CHECKS: Record<string, (value: unknown) => string[]> = {
  name: (value) => (value === null ? [NOT_NULL_MESSAGE] : textErrors(value, 'Name')),
  description: (value) =>
    value === null || typeof value === 'string' ? [] : [NOT_A_STRING_MESSAGE],
  total_quantity: (value) => {
    if (value === null) {
      return [NOT_NULL_MESSAGE]
    }
    if (!isWholeNumber(value)) {
      return [NOT_AN_INTEGER_MESSAGE]
    }
    return value < 0 ? ['Total quantity cannot be negative.'] : []
  },
  venue_id: (value) => {
    if (value === null) {
      return []
    }
    if (!isWholeNumber(value)) {
      return [NOT_AN_INTEGER_MESSAGE]
    }
    return value < 1 ? ['venue_id must be a positive number.'] : []
  },
  store_name: (value) => (value === null ? [] : textErrors(value, 'Store name')),
}

/** Every field's problems: unknown fields, wrong values, and required fields left out. */
function fieldErrors(body: Record<string, unknown>, required: readonly string[]): FieldErrors {
  const errors: FieldErrors = {}
  for (const [field, value] of Object.entries(body)) {
    const check = FIELD_CHECKS[field]
    const messages = check === undefined ? [UNKNOWN_FIELD_MESSAGE] : check(value)
    if (messages.length > 0) {
      errors[field] = messages
    }
  }
  for (const field of required) {
    if (!(field in body)) {
      errors[field] = [MISSING_MESSAGE]
    }
  }
  return errors
}

/**
 * ADR-0014's one place: a venue or a store, not both and not neither, reported on venue_id. A body
 * with neither field keeps the stored place, which only an update can send.
 */
function locationError(body: Record<string, unknown>): string | null {
  if (!('venue_id' in body) && !('store_name' in body)) {
    return null
  }
  const hasVenue = isSet(body.venue_id)
  const hasStore = isSet(body.store_name)
  if (hasVenue && hasStore) {
    return BOTH_LOCATIONS_MESSAGE
  }
  if (!hasVenue && !hasStore) {
    return NO_LOCATION_MESSAGE
  }
  return null
}

function notAnObject() {
  return errorResponse(400, 'validation_error', NOT_AN_OBJECT_MESSAGE)
}

/** The schema's 400 for this body, or null when it passes. The place is checked last. */
function bodyRefusal(body: Record<string, unknown>, required: readonly string[]) {
  const errors = fieldErrors(body, required)
  if (Object.keys(errors).length > 0) {
    return validationError(errors)
  }
  const location = locationError(body)
  if (location !== null) {
    return validationError({ venue_id: [location] })
  }
  return null
}

/** The 400 for a venue that is not in the catalogue, or null. */
function unknownVenueRefusal(body: Record<string, unknown>) {
  if (isWholeNumber(body.venue_id) && !MOCK_VENUE_IDS.includes(body.venue_id)) {
    return validationError({ venue_id: ['Venue not found.'] })
  }
  return null
}

/** `type` with the body's fields applied as the backend saves them: trimmed, a blank description as none. */
function withChanges(type: MockCatalogueType, body: Record<string, unknown>): MockCatalogueType {
  const changed = { ...type }
  if (typeof body.name === 'string') {
    changed.name = body.name.trim()
  }
  if ('description' in body) {
    const description = typeof body.description === 'string' ? body.description.trim() : ''
    changed.description = description === '' ? null : description
  }
  if (isWholeNumber(body.total_quantity)) {
    changed.total_quantity = body.total_quantity
  }
  // Sending either place replaces the whole place, so the other one is cleared.
  if ('venue_id' in body || 'store_name' in body) {
    changed.venue_id = isWholeNumber(body.venue_id) ? body.venue_id : null
    changed.store_name = typeof body.store_name === 'string' ? body.store_name.trim() : null
  }
  return changed
}

/** Save `type` in place of the one with its id, or the 409 when another type has its name. */
function save(type: MockCatalogueType, status: number) {
  if (types.some((other) => other.id !== type.id && other.name === type.name)) {
    return errorResponse(409, 'conflict', DUPLICATE_NAME_MESSAGE)
  }
  types = [...types.filter((other) => other.id !== type.id), type]
  return HttpResponse.json(type, { status })
}

/** The catalogue by name. Names are unique, so no two compare equal. */
function byName(): MockCatalogueType[] {
  return [...types].sort((first, second) => (first.name < second.name ? -1 : 1))
}

async function readJson(request: Request): Promise<unknown> {
  return request.json().catch(() => null)
}

export const equipmentCatalogueHandlers: RequestHandler[] = [
  http.get(TYPES_PATH, ({ request }) => {
    const refusal = refusalFor(request, INTERNAL_ROLES)
    if (refusal !== null) {
      return refusal
    }
    return HttpResponse.json(byName())
  }),

  http.post(TYPES_PATH, async ({ request }) => {
    const refusal = refusalFor(request, EDITOR_ROLES)
    if (refusal !== null) {
      return refusal
    }
    const sent = await readJson(request)
    if (!isRecord(sent)) {
      return notAnObject()
    }
    const body = { ...CREATE_DEFAULTS, ...sent }
    const refusedFor = bodyRefusal(body, REQUIRED_ON_CREATE) ?? unknownVenueRefusal(body)
    if (refusedFor !== null) {
      return refusedFor
    }
    // Like a Postgres sequence: an id handed to an insert that then fails is not handed out again.
    const id = nextId
    nextId += 1
    return save(withChanges({ id, ...BLANK_TYPE }, body), 201)
  }),

  http.get(TYPE_PATH, ({ request, params }) => {
    const id = idFromPath(params.equipmentTypeId)
    if (id === null) {
      return routeNotFound()
    }
    const refusal = refusalFor(request, INTERNAL_ROLES)
    if (refusal !== null) {
      return refusal
    }
    const type = types.find((candidate) => candidate.id === id)
    return type === undefined ? typeNotFound() : HttpResponse.json(type)
  }),

  http.patch(TYPE_PATH, async ({ request, params }) => {
    const id = idFromPath(params.equipmentTypeId)
    if (id === null) {
      return routeNotFound()
    }
    const refusal = refusalFor(request, EDITOR_ROLES)
    if (refusal !== null) {
      return refusal
    }
    // The backend's order: the body, then the type, then the venue, then the name.
    const body = await readJson(request)
    if (!isRecord(body)) {
      return notAnObject()
    }
    const bodyProblem = bodyRefusal(body, [])
    if (bodyProblem !== null) {
      return bodyProblem
    }
    const type = types.find((candidate) => candidate.id === id)
    if (type === undefined) {
      return typeNotFound()
    }
    return unknownVenueRefusal(body) ?? save(withChanges(type, body), 200)
  }),
]
