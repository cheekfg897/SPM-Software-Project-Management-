import { INTERNAL_ROLES, ROLE } from '@/config/roles'
import { fetchCurrentUser, logIn, register } from '@/features/auth/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { refusal, uniqueEmail, VALID_PASSWORD } from './backend'

const INVALID_CREDENTIALS_MESSAGE = 'Invalid email or password.'
/** What the backend says when sign-up names a staff role (SCRUM-88), as the mock says it too. */
const EXTERNAL_ROLE_ONLY_MESSAGE = 'Role must be one of: attendee, event_organiser.'

function newAttendee() {
  return {
    full_name: 'Integration Attendee',
    email: uniqueEmail('attendee'),
    password: VALID_PASSWORD,
    role: ROLE.ATTENDEE,
  }
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
})

describe('SCRUM-88 against the backend', () => {
  it.each(INTERNAL_ROLES)('refuses %s at sign-up, on the role field', async (role) => {
    const error = await refusal(register({ ...newAttendee(), role }))

    expect(error).toMatchObject({ status: 400, code: 'validation_error' })
    expect(error.fieldErrors).toEqual({ role: [EXTERNAL_ROLE_ONLY_MESSAGE] })
  })
})
