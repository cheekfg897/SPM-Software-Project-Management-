import { fetchEventRequest } from '@/features/eventRequests/api'
import { fieldErrorsOf } from '@/lib/api'
import type { FieldErrors } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { mockTokenFor } from '../../fixtures/accounts'
import type { MockAccount } from '../../fixtures/accounts'

/**
 * Shared by the mock tests of the review actions (eventReview.test.ts and
 * eventClarification.test.ts): who calls, what a request's status is now, and the refusals
 * every route gives, worded as the backend words them.
 */

export const NOT_FOUND = { status: 404, code: 'not_found', message: 'Event request not found.' }
export const NOT_PERMITTED = { status: 403, code: 'authorization_error' }
export const NOT_SIGNED_IN = { status: 401, code: 'authentication_error' }
export const NOT_AN_OBJECT = {
  status: 400,
  code: 'validation_error',
  message: 'Request body must be a JSON object.',
}

/** Send every later call as `account`, or with no token for null. */
export function signInAs(account: MockAccount | null) {
  sendRequestsAs(account === null ? null : mockTokenFor(account))
}

/** The request's status as the signed-in caller reads it now. */
export async function statusOf(reference: string) {
  return (await fetchEventRequest(reference)).status
}

/** Check `error` is the backend's 400 with exactly these per-field messages. */
export function expectInvalid(error: unknown, details: FieldErrors) {
  expect(error).toMatchObject({
    status: 400,
    code: 'validation_error',
    message: 'Invalid request.',
  })
  expect(fieldErrorsOf(error)).toEqual(details)
}

/** Check `error` is the backend's 400 for a body that isn't a JSON object, with no fields. */
export function expectNotAnObject(error: unknown) {
  expect(error).toMatchObject(NOT_AN_OBJECT)
  expect(fieldErrorsOf(error)).toEqual({})
}
