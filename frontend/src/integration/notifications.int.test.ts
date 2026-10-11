import { logIn, register } from '@/features/auth/api'
import {
  fetchNotifications,
  fetchUnreadCount,
  markNotificationRead,
} from '@/features/notifications/api'
import { ROLE } from '@/config/roles'
import { ApiError } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { uniqueEmail, VALID_PASSWORD } from './backend'

/** An id no notification has, so marking it read is a 404. */
const MISSING_NOTIFICATION_ID = 2_000_000_000

/** Sign a brand-new attendee up and send every later request as them. */
async function signInAsNewAttendee() {
  const email = uniqueEmail('notified')
  await register({
    full_name: 'Integration Attendee',
    email,
    password: VALID_PASSWORD,
    role: ROLE.ATTENDEE,
  })
  const session = await logIn({ email, password: VALID_PASSWORD })
  sendRequestsAs(session.access_token)
}

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

afterEach(() => sendRequestsAs(null))

describe('SCRUM-28 notifications against the backend', () => {
  it('gives a new user an empty list and an unread count of 0', async () => {
    await signInAsNewAttendee()

    await expect(fetchNotifications()).resolves.toEqual([])
    await expect(fetchUnreadCount()).resolves.toBe(0)
  })

  it('refuses the list, the count and marking read without a token', async () => {
    const calls = [fetchNotifications(), fetchUnreadCount(), markNotificationRead(1)]

    for (const call of calls) {
      expect(await refusal(call)).toMatchObject({ status: 401, code: 'authentication_error' })
    }
  })

  it('answers 404 when marking a notification that does not exist', async () => {
    await signInAsNewAttendee()

    const error = await refusal(markNotificationRead(MISSING_NOTIFICATION_ID))

    expect(error.status).toBe(404)
  })

  it.todo(
    'lists a real notification newest first and marks it read (needs a staff action to raise one)',
  )
})
