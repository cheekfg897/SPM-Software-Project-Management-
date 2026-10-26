import { INTERNAL_ROLES, ROLE } from '@/config/roles'
import { fetchCurrentUser, logIn, logOut, register } from '@/features/auth/api'
import { fetchNotifications } from '@/features/notifications/api'
import { createOrganisation } from '@/features/organisations/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import {
  hasTechSupport,
  newOrganiser,
  refusal,
  signInAs,
  signInAsTechSupport,
  staffAccount,
  uniqueEmail,
  VALID_PASSWORD,
} from './backend'
import type { Credentials } from './backend'

/** An organisation id no database has. */
const UNKNOWN_ORGANISATION_ID = 99_999_999

const INVALID_CREDENTIALS_MESSAGE = 'Invalid email or password.'
/** The backend's 401 for a missing, invalid, expired or logged-out token (ADR-0110). */
const INVALID_TOKEN = {
  status: 401,
  code: 'authentication_error',
  message: 'Missing, invalid or expired token.',
}
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

/** Sign a new attendee up, and return their details for logging in. */
async function registeredAttendee(): Promise<Credentials> {
  const attendee = newAttendee()
  await register(attendee)
  return { email: attendee.email, password: attendee.password }
}

/** Log in and return the token, without sending it yet: one call is one device's session. */
async function tokenFor(credentials: Credentials): Promise<string> {
  const session = await logIn(credentials)
  return session.access_token
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

  it('signs up an Event Organiser with an existing organisation_id (SCRUM-66)', async () => {
    await signInAs(staffAccount())
    const organisation = await createOrganisation({
      name: `Integration organisation ${uniqueEmail('organisation')}`,
      contact_name: 'Integration Contact',
      contact_email: uniqueEmail('contact'),
    })
    sendRequestsAs(null)
    const organiser = newOrganiser(organisation.id)

    await register(organiser)
    await signInAs({ email: organiser.email, password: organiser.password })

    expect(await fetchCurrentUser()).toMatchObject({
      role: ROLE.EVENT_ORGANISER,
      organisation_id: organisation.id,
    })
  })

  it.each([
    ['without one', null, 'Event Organisers must belong to a client organisation.'],
    ['with an unknown one', UNKNOWN_ORGANISATION_ID, 'Client organisation not found.'],
  ])(
    'refuses an Event Organiser %s, on organisation_id (SCRUM-66)',
    async (_case, organisationId, message) => {
      const error = await refusal(register(newOrganiser(organisationId)))

      expect(error).toMatchObject({ status: 400, code: 'validation_error' })
      expect(error.fieldErrors).toEqual({ organisation_id: [message] })
    },
  )
})

describe('SCRUM-88 against the backend', () => {
  it.each(INTERNAL_ROLES)('refuses %s at sign-up, on the role field', async (role) => {
    const error = await refusal(register({ ...newAttendee(), role }))

    expect(error).toMatchObject({ status: 400, code: 'validation_error' })
    expect(error.fieldErrors).toEqual({ role: [EXTERNAL_ROLE_ONLY_MESSAGE] })
  })
})

describe('SCRUM-89 against the backend', () => {
  it('logs out with no content, after which that token is refused everywhere', async () => {
    sendRequestsAs(await tokenFor(await registeredAttendee()))

    await expect(logOut()).resolves.toBeUndefined()

    expect(await refusal(fetchCurrentUser())).toMatchObject(INVALID_TOKEN)
    expect(await refusal(fetchNotifications())).toMatchObject(INVALID_TOKEN)
  })

  it('leaves the same user’s other session and other users signed in', async () => {
    const credentials = await registeredAttendee()
    const loggedOut = await tokenFor(credentials)
    const otherDevice = await tokenFor(credentials)
    const otherUser = await tokenFor(await registeredAttendee())

    sendRequestsAs(loggedOut)
    await logOut()

    sendRequestsAs(otherDevice)
    expect(await fetchCurrentUser()).toMatchObject({ email: credentials.email })
    sendRequestsAs(otherUser)
    expect(await fetchCurrentUser()).toMatchObject({ role: ROLE.ATTENDEE })
  })

  it('refuses a logout without a token, or with a token already logged out', async () => {
    const withoutToken = await refusal(logOut())
    sendRequestsAs(await tokenFor(await registeredAttendee()))
    await logOut()
    const again = await refusal(logOut())

    expect(withoutToken).toMatchObject(INVALID_TOKEN)
    expect(again).toMatchObject(INVALID_TOKEN)
  })

  it('logs out a member of staff', async () => {
    sendRequestsAs(await tokenFor(staffAccount()))

    await logOut()

    expect(await refusal(fetchCurrentUser())).toMatchObject(INVALID_TOKEN)
  })

  it.skipIf(!hasTechSupport)('logs out Technical Support', async () => {
    await signInAsTechSupport()

    await logOut()

    expect(await refusal(fetchCurrentUser())).toMatchObject(INVALID_TOKEN)
  })
})
