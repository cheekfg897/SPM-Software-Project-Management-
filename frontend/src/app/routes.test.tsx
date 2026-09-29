import { screen, within } from '@testing-library/react'

import { ROUTES } from '@/config/routes'
import { ROLE } from '@/config/roles'
import { renderApp } from '@/test/render'

const ATTENDEE = {
  accessToken: 'abc',
  user: { id: 3, full_name: 'Alice Tan', role: ROLE.ATTENDEE },
}

describe('app routes', () => {
  it.each(Object.values(ROUTES))('%s renders a page with a heading', async (path) => {
    renderApp(path)

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
