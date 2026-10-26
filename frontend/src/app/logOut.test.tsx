import { onlineManager } from '@tanstack/react-query'
import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { ROUTES } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor, mockTokenFor } from '@/mocks/fixtures/accounts'
import { notAuthenticated } from '@/mocks/responses'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

/**
 * SCRUM-6 AC4 with SCRUM-89: Log out asks the backend to revoke the token, sending it while the
 * session still holds it, then signs out here and goes to the front page as before. If the
 * backend can't be reached or refuses the token, the user is signed out here all the same
 * (ADR-0110).
 */

const LOGOUT_PATH = '/api/auth/logout'
const ATTENDEE = MOCK_ACCOUNTS.attendee

async function clickLogOut() {
  const rendered = renderApp(ROUTES.EVENTS, { session: mockSessionFor(ATTENDEE) })
  const header = within(screen.getByRole('banner'))
  await rendered.user.click(header.getByRole('button', { name: 'Log out' }))
  return { ...rendered, header }
}

async function expectSignedOutAtHome({
  store,
  router,
  header,
}: Awaited<ReturnType<typeof clickLogOut>>) {
  await waitFor(() => expect(header.getByRole('link', { name: 'Log in' })).toBeInTheDocument())
  expect(store.getState().session.accessToken).toBeNull()
  expect(router.state.location.pathname).toBe(ROUTES.HOME)
}

afterEach(() => onlineManager.setOnline(true))

describe('SCRUM-89 logging out', () => {
  it('sends the logout with the session’s token, then signs out to the front page', async () => {
    const requests = recordRequests()

    const loggedOut = await clickLogOut()

    await expectSignedOutAtHome(loggedOut)
    const logouts = requests.filter((request) => new URL(request.url).pathname === LOGOUT_PATH)
    expect(logouts.map((request) => request.method)).toEqual(['POST'])
    expect(logouts[0]?.headers.get('Authorization')).toBe(`Bearer ${mockTokenFor(ATTENDEE)}`)
  })

  it.each([
    ['the backend can’t be reached', () => HttpResponse.error()],
    ['the backend refuses the token', () => notAuthenticated()],
  ])('signs out here anyway when %s', async (_case, answer) => {
    server.use(http.post(LOGOUT_PATH, answer))

    const loggedOut = await clickLogOut()

    await expectSignedOutAtHome(loggedOut)
  })

  it('signs out at once while the browser is offline, rather than waiting to be online', async () => {
    onlineManager.setOnline(false)

    const loggedOut = await clickLogOut()

    await expectSignedOutAtHome(loggedOut)
  })
})
