import { ROLE } from '@/config/roles'
import { fetchCurrentUser, logIn, register } from '@/features/auth/api'
import { ApiError } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { uniqueEmail, VALID_PASSWORD } from './backend'

const INVALID_CREDENTIALS_MESSAGE = 'Invalid email or password.'

function newAttendee() {
  return {
    full_name: 'Integration Attendee',
    email: uniqueEmail('attendee'),
    password: VALID_PASSWORD,
    role: ROLE.ATTENDEE,
  }
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

describe('SCRUM-65 and SCRUM-6 against the backend', () => {
  it('signs up an attendee, logs them in, and knows who they are', async () => {
    const attendee = newAttendee()

    await register(attendee)
    const session = await logIn({ email: attendee.email, password: attendee.password })
    sendRequestsAs(session.access_token)
    const currentUser = await fetchCurrentUser()

    expect(session).toEqual({
      access_token: expect.any(String) as string,
      token_type: 'Bearer',
      user: { id: expect.any(Number) as number, full_name: attendee.full_name, role: 'attendee' },
    })
    expect(currentUser).toMatchObject({
      id: session.user.id,
      email: attendee.email,
      full_name: attendee.full_name,
      role: 'attendee',
    })
  })

  it('refuses an email that is already in use', async () => {
    const attendee = newAttendee()
    await register(attendee)

    const error = await refusal(register({ ...attendee, full_name: 'Someone Else' }))

    expect(error).toMatchObject({ status: 409, code: 'conflict' })
    expect(error.message).toMatch(/already exists/)
  })

  it('refuses a wrong password and an unknown email with the same message', async () => {
    const attendee = newAttendee()
    await register(attendee)

    const wrongPassword = await refusal(logIn({ email: attendee.email, password: 'Wrong12345' }))
    const unknownEmail = await refusal(
      logIn({ email: uniqueEmail('nobody'), password: VALID_PASSWORD }),
    )

    expect(wrongPassword).toMatchObject({ status: 401, code: 'authentication_error' })
    expect(wrongPassword.message).toBe(INVALID_CREDENTIALS_MESSAGE)
    expect(unknownEmail.message).toBe(INVALID_CREDENTIALS_MESSAGE)
  })

  it('names each field it refuses', async () => {
    const error = await refusal(
      register({ full_name: '', email: 'not-an-email', password: 'short', role: ROLE.ATTENDEE }),
    )

    expect(error).toMatchObject({ status: 400, code: 'validation_error' })
    expect(Object.keys(error.fieldErrors)).toEqual(
      expect.arrayContaining(['full_name', 'email', 'password']),
    )
  })

  it('refuses /me without a token, in the error shape the client reads', async () => {
    const error = await refusal(fetchCurrentUser())

    expect(error).toMatchObject({ status: 401, code: 'authentication_error' })
  })

  it.todo('signs up an Event Organiser with an existing organisation_id (lands with SCRUM-66)')
  it.todo('refuses an Event Organiser without an organisation_id, on that field (SCRUM-66)')
  it.todo('refuses an unknown organisation_id, on that field (SCRUM-66)')
  it.todo('refuses a staff role at sign-up, on the role field (lands with SCRUM-88)')
})
