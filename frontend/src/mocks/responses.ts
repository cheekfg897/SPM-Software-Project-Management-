import { HttpResponse } from 'msw'

import type { FieldErrors } from '@/lib/api'

/** The backend's message for a missing, invalid or expired token (app/common/errors.py). */
export const INVALID_TOKEN_MESSAGE = 'Missing, invalid or expired token.'

/** The backend's message when a signed-in user's role may not use a route (app/common/decorators.py). */
export const NOT_PERMITTED_MESSAGE = 'You do not have permission to perform this action.'

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
