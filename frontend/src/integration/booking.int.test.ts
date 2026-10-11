import { ROLE } from '@/config/roles'
import { fetchBookingRequests, raiseBookingRequest } from '@/features/booking/api'
import { logIn, register } from '@/features/auth/api'
import { ApiError } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { uniqueEmail, VALID_PASSWORD } from './backend'

/** A well-formed reference no database has, so the lookup finds nothing. */
const UNKNOWN_EVENT_REFERENCE = 'EVR-NOSUCH00'
const NOT_FOUND_MESSAGE = 'Event request not found.'

/**
 * Event Coordinators are created by `flask create-staff-user` (SCRUM-88), not by sign-up, so
 * the checks that need one read a seeded account from these variables and skip without them:
 * COORDINATOR_EMAIL=... COORDINATOR_PASSWORD=... npm run test:integration
 */
const COORDINATOR_EMAIL = import.meta.env.VITE_COORDINATOR_EMAIL
const COORDINATOR_PASSWORD = import.meta.env.VITE_COORDINATOR_PASSWORD
const hasCoordinator = Boolean(COORDINATOR_EMAIL) && Boolean(COORDINATOR_PASSWORD)

/** The ApiError a call was refused with. Fails the test if it succeeded or failed another way. */
async function refusal(call: Promise<unknown>): Promise<ApiError> {
  const error = await call.then(
    () => expect.fail('Expected the backend to refuse the request.'),
    (caught: unknown) => caught,
  )
  if (!(error instanceof ApiError)) {
    throw new Error(`Expected an ApiError, got ${String(error)}`)
  }
  return error
}

async function signInAsAttendee() {
  const credentials = { email: uniqueEmail('attendee'), password: VALID_PASSWORD }
  await register({ full_name: 'Integration Attendee', role: ROLE.ATTENDEE, ...credentials })
  const session = await logIn(credentials)
  sendRequestsAs(session.access_token)
}

async function signInAsCoordinator() {
  const session = await logIn({
    email: COORDINATOR_EMAIL ?? '',
    password: COORDINATOR_PASSWORD ?? '',
  })
  sendRequestsAs(session.access_token)
}

afterEach(() => sendRequestsAs(null))

describe('SCRUM-42 venue booking requests against the backend', () => {
  it('refuses listing without a token (401)', async () => {
    const error = await refusal(fetchBookingRequests(UNKNOWN_EVENT_REFERENCE))

    expect(error).toMatchObject({ status: 401, code: 'authentication_error' })
  })

  it('refuses a role other than the Event Coordinator (403)', async () => {
    await signInAsAttendee()

    const error = await refusal(fetchBookingRequests(UNKNOWN_EVENT_REFERENCE))

    expect(error).toMatchObject({ status: 403, code: 'authorization_error' })
  })

  it.skipIf(!hasCoordinator)('answers 404 for an event the coordinator has none of', async () => {
    await signInAsCoordinator()

    const error = await refusal(fetchBookingRequests(UNKNOWN_EVENT_REFERENCE))

    expect(error).toMatchObject({ status: 404, code: 'not_found', message: NOT_FOUND_MESSAGE })
  })

  it.skipIf(!hasCoordinator)(
    'names each field it refuses (400), before looking for the event',
    async () => {
      await signInAsCoordinator()

      const error = await refusal(
        raiseBookingRequest(UNKNOWN_EVENT_REFERENCE, {
          venue_id: 1,
          starts_at: '2026-11-10T09:00:00+08:00',
          ends_at: '2026-11-10T12:00:00+08:00',
          purpose: 'Keynote',
          justification: '   ',
        }),
      )

      expect(error).toMatchObject({ status: 400, code: 'validation_error' })
      expect(Object.keys(error.fieldErrors)).toEqual(['justification'])
    },
  )

  it.todo('raises a request for an approved event and lists it (needs a seeded approved event)')
  it.todo('refuses a second Pending request for the same venue and period (409)')
})
