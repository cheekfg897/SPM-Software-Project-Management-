import { isRecord } from '@/lib/isRecord'

/** Messages per field, keyed by the field's name (a dotted path for nested fields). */
export type FieldErrors = Record<string, string[]>

export const NETWORK_ERROR_CODE = 'network_error'
export const NETWORK_ERROR_MESSAGE =
  "Can't reach ConnectSphere. Check your connection and try again."
export const UNEXPECTED_RESPONSE_CODE = 'unexpected_response'
export const UNEXPECTED_RESPONSE_MESSAGE = 'Something went wrong. Please try again.'

/**
 * An error response from the backend, or a failure to reach it.
 *
 * `code` and `message` are the backend's `error` and `message`; screens show `message` as it
 * is rather than writing their own. `status` is 0 when no response arrived at all. `details` is
 * the body's `details` as sent, for a refusal that carries more than per-field messages, such as
 * when withdrawals closed (SCRUM-53).
 */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly fieldErrors: FieldErrors
  readonly details: Record<string, unknown>

  constructor(
    status: number,
    code: string,
    message: string,
    fieldErrors: FieldErrors = {},
    details: Record<string, unknown> = {},
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.fieldErrors = fieldErrors
    this.details = details
  }

  /** A 4xx: the request itself was refused, so sending it again won't help. */
  get isClientError(): boolean {
    return this.status >= 400 && this.status < 500
  }
}

function isMessageList(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string')
}

/**
 * Flatten the backend's validation `details` (marshmallow's messages) into one list of
 * messages per field. A nested field is named by its path, e.g. `venue.capacity`.
 */
function collectFieldErrors(details: Record<string, unknown>, pathPrefix = ''): FieldErrors {
  const fieldErrors: FieldErrors = {}
  for (const [field, value] of Object.entries(details)) {
    const path = pathPrefix + field
    if (isMessageList(value)) {
      fieldErrors[path] = value
    } else if (isRecord(value)) {
      Object.assign(fieldErrors, collectFieldErrors(value, `${path}.`))
    }
  }
  return fieldErrors
}

/** Every backend error body: `{"error", "message", "details?"}` (app/common/errors.py). */
interface BackendErrorBody {
  error: string
  message: string
  details?: unknown
}

function isBackendErrorBody(body: unknown): body is BackendErrorBody {
  return isRecord(body) && typeof body.error === 'string' && typeof body.message === 'string'
}

/** Build an ApiError from an error response's status and decoded body. */
export function toApiError(status: number, body: unknown): ApiError {
  if (!isBackendErrorBody(body)) {
    return new ApiError(status, UNEXPECTED_RESPONSE_CODE, UNEXPECTED_RESPONSE_MESSAGE)
  }

  const details = isRecord(body.details) ? body.details : {}
  return new ApiError(status, body.error, body.message, collectFieldErrors(details), details)
}

/** The message to show for any error: the backend's own, or a generic one. */
export function errorMessageOf(error: unknown): string {
  return error instanceof ApiError ? error.message : UNEXPECTED_RESPONSE_MESSAGE
}

/** The backend's messages per field, or none when the error isn't a validation error. */
export function fieldErrorsOf(error: unknown): FieldErrors {
  return error instanceof ApiError ? error.fieldErrors : {}
}

/** One of the error's `details` that is text, or null when it is missing, not text or not an ApiError. */
export function textDetailOf(error: unknown, name: string): string | null {
  if (!(error instanceof ApiError)) {
    return null
  }
  const detail = error.details[name]
  return typeof detail === 'string' ? detail : null
}
