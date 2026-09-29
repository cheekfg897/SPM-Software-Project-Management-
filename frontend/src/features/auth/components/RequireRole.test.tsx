import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { ROUTES } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/handlers/auth'
import { server } from '@/mocks/server'
import { renderApp } from '@/test/render'

function currentUrl(router: ReturnType<typeof renderApp>['router']): string {
  return router.state.location.pathname + router.state.location.search
}

describe('SCRUM-6 pages only a role may open', () => {
  it('sends a visitor to log in, and remembers the page', async () => {
    const { router } = renderApp(ROUTES.ORGANISER_HOME)

    await screen.findByRole('heading', { name: 'Log in' })
    expect(currentUrl(router)).toBe('/login?next=%2Forganiser')
  })

  it('sends a visitor to the staff log-in page for a staff page', async () => {
    const { router } = renderApp(ROUTES.STAFF_HOME)

    await screen.findByRole('heading', { name: 'Staff log in' })
    expect(currentUrl(router)).toBe('/staff/login?next=%2Fstaff')
  })

  it('sends someone with another role to their own landing view', async () => {
    const { router } = renderApp(ROUTES.STAFF_HOME, {
      session: mockSessionFor(MOCK_ACCOUNTS.attendee),
    })

    await waitFor(() => expect(router.state.location.pathname).toBe(ROUTES.EVENTS))
  })

  it('greets the right role by the name the backend has for them', async () => {
    renderApp(ROUTES.ORGANISER_HOME, { session: mockSessionFor(MOCK_ACCOUNTS.organiser) })

    expect(
      await screen.findByText(`Welcome back, ${MOCK_ACCOUNTS.organiser.full_name}.`),
    ).toBeInTheDocument()
  })

  it("shows the backend's message when it can't load the user", async () => {
    server.use(
      http.get('/api/auth/me', () =>
        HttpResponse.json({ error: 'not_found', message: 'User not found.' }, { status: 404 }),
      ),
    )
    renderApp(ROUTES.STAFF_HOME, { session: mockSessionFor(MOCK_ACCOUNTS.coordinator) })

    expect(await screen.findByRole('alert')).toHaveTextContent('User not found.')
  })
})
