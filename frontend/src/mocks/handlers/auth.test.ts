import { ROLE } from '@/config/roles'
import { fetchCurrentUser, logIn, logOut } from '@/features/auth/api'
import { fetchNotifications } from '@/features/notifications/api'
import { refusalOf } from '@/test/refusalOf'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { MOCK_ACCOUNTS, mockTokenFor } from '../fixtures/accounts'
import type { MockAccount } from '../fixtures/accounts'
import { INVALID_TOKEN_MESSAGE } from '../responses'

/**
 * The logout mock stands in for SCRUM-89's backend (`POST /api/auth/logout`, ADR-0110): the
 * token sent is refused from then on, by every mock handler that reads the caller.
 */

/** One account of each role, written out so a role added later needs one here. */
const ONE_ACCOUNT_PER_ROLE: MockAccount[] = [
  MOCK_ACCOUNTS.organiser,
  MOCK_ACCOUNTS.attendee,
  MOCK_ACCOUNTS.coordinator,
  MOCK_ACCOUNTS.lead,
  MOCK_ACCOUNTS.venueStaff,
  MOCK_ACCOUNTS.technicalSupport,
  MOCK_ACCOUNTS.safetyOfficer,
]

const INVALID_TOKEN = { status: 401, code: 'authentication_error', message: INVALID_TOKEN_MESSAGE }

function sendAs(account: MockAccount): void {
  sendRequestsAs(mockTokenFor(account))
}

describe('SCRUM-89 logout mock', () => {
  it('has an account for every role', () => {
    const roles = ONE_ACCOUNT_PER_ROLE.map((account) => account.role)

    expect([...roles].sort()).toEqual(Object.values(ROLE).sort())
  })

  it.each(ONE_ACCOUNT_PER_ROLE)('logs $role out with no content', async (account) => {
    sendAs(account)

    await expect(logOut()).resolves.toBeUndefined()
  })

  it('refuses the logged-out token on /me and on another feature’s routes', async () => {
    sendAs(MOCK_ACCOUNTS.attendee)
    await logOut()

    expect(await refusalOf(fetchCurrentUser())).toMatchObject(INVALID_TOKEN)
    expect(await refusalOf(fetchNotifications())).toMatchObject(INVALID_TOKEN)
  })

  it('leaves other accounts signed in', async () => {
    sendAs(MOCK_ACCOUNTS.attendee)
    await logOut()

    sendAs(MOCK_ACCOUNTS.organiser)

    expect(await fetchCurrentUser()).toMatchObject({ id: MOCK_ACCOUNTS.organiser.id })
  })

  it('refuses a logout without a token, or with the logged-out one', async () => {
    sendRequestsAs(null)
    const withoutToken = await refusalOf(logOut())
    sendAs(MOCK_ACCOUNTS.attendee)
    await logOut()
    const again = await refusalOf(logOut())

    expect(withoutToken).toMatchObject(INVALID_TOKEN)
    expect(again).toMatchObject(INVALID_TOKEN)
  })

  it('accepts the token again once the account logs in again', async () => {
    const attendee = MOCK_ACCOUNTS.attendee
    sendAs(attendee)
    await logOut()

    const session = await logIn({ email: attendee.email, password: attendee.password })
    sendRequestsAs(session.access_token)

    expect(await fetchCurrentUser()).toMatchObject({ id: attendee.id })
  })
})
