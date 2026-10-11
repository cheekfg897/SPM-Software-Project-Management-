import { screen, within } from '@testing-library/react'

import { ROUTES } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import { eventEquipmentPath, ROUTES } from '@/config/routes'
import { ROLE } from '@/config/roles'
import { renderApp } from '@/test/render'

// A token the mock backend accepts: the header now asks it for the unread count.
const ATTENDEE = mockSessionFor(MOCK_ACCOUNTS.attendee)

/** A path a visitor could open: the equipment route needs an event reference filled in. */
function openablePath(path: string): string {
  return path === ROUTES.EVENT_EQUIPMENT ? eventEquipmentPath('EVR-ROUTE0001') : path
}

describe('app routes', () => {
  it.each(Object.values(ROUTES))('%s renders a page with a heading', async (path) => {
    renderApp(openablePath(path))

    expect(await screen.findByRole('heading', { level: 1 })).toBeInTheDocument()
  })

  it('shows a not found page for an unknown path', () => {
    renderApp('/nowhere')

    expect(screen.getByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
  })

  it('offers log in and sign up to a visitor', () => {
    renderApp(ROUTES.HOME)

    const header = within(screen.getByRole('banner'))
    expect(header.getByRole('link', { name: 'Log in' })).toHaveAttribute('href', ROUTES.LOGIN)
    expect(header.getByRole('link', { name: 'Sign up' })).toHaveAttribute('href', ROUTES.SIGN_UP)
  })

  it('points staff to their own log in page', () => {
    renderApp(ROUTES.HOME)

    expect(screen.getByRole('link', { name: 'Staff log in' })).toHaveAttribute(
      'href',
      ROUTES.STAFF_LOGIN,
    )
  })

  it('shows who is signed in, and logs them out', async () => {
    const { user, store, router } = renderApp(ROUTES.EVENTS, { session: ATTENDEE })

    const header = within(screen.getByRole('banner'))
    expect(header.getByText('Alice Tan')).toBeInTheDocument()

    await user.click(header.getByRole('button', { name: 'Log out' }))

    expect(store.getState().session.accessToken).toBeNull()
    expect(router.state.location.pathname).toBe(ROUTES.HOME)
    expect(header.getByRole('link', { name: 'Log in' })).toBeInTheDocument()
  })
})
