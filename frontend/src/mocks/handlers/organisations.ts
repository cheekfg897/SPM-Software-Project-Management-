import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'

import { INTERNAL_ROLES } from '@/config/roles'
import type { ClientOrganisation } from '@/features/organisations/api'
import type { FieldErrors } from '@/lib/api'

import {
  errorResponse,
  notAllowed,
  notAuthenticated,
  readBody,
  validationError,
} from '../responses'

import { accountForRequest } from './auth'
import { MOCK_ORGANISATIONS } from './organisationFixtures'

/**
 * The organisations module's endpoints (SCRUM-66), answering as
 * backend/app/modules/organisations/routes.py, schemas.py and services.py do: staff only,
 * listed by name, and every field refused with the schema's own message.
 */

const ORGANISATIONS_PATH = '/api/organisations'
const DUPLICATE_NAME_MESSAGE = 'A client organisation with this name already exists.'
const MISSING_MESSAGE = 'Missing data for required field.'
const PHONE_RULE_MESSAGE =
  'Contact phone must have at least 7 digits and use only spaces, hyphens, brackets and a leading +.'
const PHONE_MIN_DIGITS = 7
const PHONE_CHARACTERS = /^\+?[0-9 ()-]+$/
/** Looser than marshmallow's Email: one @ with something either side and no spaces. */
const EMAIL_SHAPE = /^[^@\s]+@[^@\s]+$/
const FIELDS = ['name', 'contact_name', 'contact_email', 'contact_phone']
const REQUIRED_FIELDS = ['name', 'contact_name', 'contact_email']
/** Each field's longest value and the message for one longer (organisations/models.py). */
const MAX_LENGTHS: Record<string, { max: number; message: string }> = {
  name: { max: 120, message: 'Name must be at most 120 characters.' },
  contact_name: { max: 120, message: 'Contact name must be at most 120 characters.' },
  contact_email: { max: 255, message: 'Contact email must be at most 255 characters.' },
  contact_phone: { max: 30, message: 'Contact phone must be at most 30 characters.' },
}

let organisations: ClientOrganisation[] = []

/** Forget the organisations recorded since, and put the starting ones back. Runs after every test. */
export function resetMockOrganisations(): void {
  organisations = MOCK_ORGANISATIONS.map((organisation) => ({ ...organisation }))
}

resetMockOrganisations()

/** Whether the caller is staff, who alone see organisations (AC5); otherwise the response to send. */
function checkStaff(request: Request) {
  const user = accountForRequest(request)
  if (user === undefined) {
    return notAuthenticated()
  }
  if (!INTERNAL_ROLES.includes(user.role)) {
    return notAllowed()
  }
  return null
}

function byName(): ClientOrganisation[] {
  return [...organisations].sort((left, right) => left.name.localeCompare(right.name))
}

function phoneRuleBroken(phone: string): boolean {
  const trimmed = phone.trim()
  if (trimmed === '') {
    return false
  }
  const digits = trimmed.replace(/[^0-9]/g, '').length
  return !PHONE_CHARACTERS.test(trimmed) || digits < PHONE_MIN_DIGITS
}

/** What the field's own validators say about a string value; marshmallow runs every one. */
function stringMessages(field: string, value: string): string[] {
  const messages: string[] = []
  if (field === 'contact_email' && !EMAIL_SHAPE.test(value)) {
    messages.push('Not a valid email address.')
  }
  if ((field === 'name' || field === 'contact_name') && value.trim() === '') {
    messages.push('Must not be blank.')
  }
  const limit = MAX_LENGTHS[field]
  if (limit !== undefined && value.length > limit.max) {
    messages.push(limit.message)
  }
  if (field === 'contact_phone' && phoneRuleBroken(value)) {
    messages.push(PHONE_RULE_MESSAGE)
  }
  return messages
}

/** The messages for one field that was sent; an empty list when it is fine. */
function fieldMessages(field: string, value: unknown): string[] {
  if (!FIELDS.includes(field)) {
    return ['Unknown field.']
  }
  if (value === null) {
    return field === 'contact_phone' ? [] : ['Field may not be null.']
  }
  if (typeof value !== 'string') {
    return field === 'contact_email' ? ['Not a valid email address.'] : ['Not a valid string.']
  }
  return stringMessages(field, value)
}

/** CreateClientOrganisationSchema's refusals, per field. */
function organisationErrors(body: Record<string, unknown>): FieldErrors {
  const errors: FieldErrors = {}
  for (const field of REQUIRED_FIELDS) {
    if (body[field] === undefined) {
      errors[field] = [MISSING_MESSAGE]
    }
  }
  for (const [field, value] of Object.entries(body)) {
    const messages = fieldMessages(field, value)
    if (messages.length > 0) {
      errors[field] = messages
    }
  }
  return errors
}

/** The organisation as the schema's post_load leaves it: names trimmed, a blank phone as none. */
function toOrganisation(body: Record<string, unknown>): ClientOrganisation {
  const phone = typeof body.contact_phone === 'string' ? body.contact_phone.trim() : ''
  const highestId = Math.max(0, ...organisations.map((organisation) => organisation.id))
  return {
    id: highestId + 1,
    name: String(body.name).trim(),
    contact_name: String(body.contact_name).trim(),
    contact_email: String(body.contact_email),
    contact_phone: phone === '' ? null : phone,
    created_at: new Date().toISOString(),
  }
}

export const organisationHandlers: RequestHandler[] = [
  http.get(ORGANISATIONS_PATH, ({ request }) => {
    const refusal = checkStaff(request)
    return refusal ?? HttpResponse.json({ organisations: byName() })
  }),

  http.post(ORGANISATIONS_PATH, async ({ request }) => {
    const refusal = checkStaff(request)
    if (refusal !== null) {
      return refusal
    }
    const body = await readBody(request)
    const errors = organisationErrors(body)
    if (Object.keys(errors).length > 0) {
      return validationError(errors)
    }

    const created = toOrganisation(body)
    // Names are unique exactly as typed, once trimmed (ADR-0013).
    if (organisations.some((existing) => existing.name === created.name)) {
      return errorResponse(409, 'conflict', DUPLICATE_NAME_MESSAGE)
    }
    organisations.push(created)
    return HttpResponse.json(created, { status: 201 })
  }),
]
