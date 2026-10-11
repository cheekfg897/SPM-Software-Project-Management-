import { HttpResponse } from 'msw'

import type { FieldErrors } from '@/lib/api'
import { isRecord } from '@/lib/isRecord'

/** The backend's message for a missing, invalid or expired token (app/common/errors.py). */
const INVALID_TOKEN_MESSAGE = 'Missing, invalid or expired token.'

/** An error in the backend's shape: `{"error", "message", "details?"}`. */
export function errorResponse(status: number, error: string, message: string) {
  return HttpResponse.json({ error, message }, { status })
}

/** A 400 with per-field messages, as the backend's load_or_raise sends it. */
export function validationError(details: FieldErrors) {
  return HttpResponse.json(
    { error: 'validation_error', message: 'Invalid request.', details },
    { status: 400 },
  )
}

/** The 401 for a request without a valid token. */
export function notAuthenticated() {
  return errorResponse(401, 'authentication_error', INVALID_TOKEN_MESSAGE)
}

/** The 403 for a signed-in user whose role may not do this. */
export function notAllowed() {
  return errorResponse(
    403,
    'authorization_error',
    'You do not have permission to perform this action.',
  )
}

/** A request's JSON body as an object; anything else (no body, bad JSON) reads as empty. */
export async function readBody(request: Request): Promise<Record<string, unknown>> {
  const body: unknown = await request.json().catch(() => null)
  return isRecord(body) ? body : {}
}
