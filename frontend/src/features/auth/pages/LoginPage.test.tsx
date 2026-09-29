import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { ROUTES } from '@/config/routes'
import { INVALID_CREDENTIALS_MESSAGE, MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/handlers/auth'
import { server } from '@/mocks/server'
import { renderApp } from '@/test/render'

import { logInThroughForm } from '../test/logInThroughForm'

describe('SCRUM-6 log in (organisers and attendees)', () => {
  it('logs an attendee in and takes them to the events', async () => {
    const app = renderApp(ROUTES.LOGIN)
    const { attendee } = MOCK_ACCOUNTS

    await logInThroughForm(app.user, attendee)

    await waitFor(() => expect(app.router.state.location.pathname).toBe(ROUTES.EVENTS))
    expect(app.store.getState().session.user).toEqual(mockSessionFor(attendee).user)
  })

  it('takes an organiser to their own landing view', async () => {
    const app = renderApp(ROUTES.LOGIN)
    const { organiser } = MOCK_ACCOUNTS

    await logInThroughForm(app.user, organiser)

    expect(await screen.findByText(`Welcome back, ${organiser.full_name}.`)).toBeInTheDocument()
    expect(app.router.state.location.pathname).toBe(ROUTES.ORGANISER_HOME)
  })

  it('refuses a wrong password without saying which detail was wrong', async () => {
    const app = renderApp(ROUTES.LOGIN)

    await logInThroughForm(app.user, { ...MOCK_ACCOUNTS.attendee, password: 'WrongPassword1' })

    expect(await screen.findByRole('alert')).toHaveTextContent(INVALID_CREDENTIALS_MESSAGE)
    expect(app.store.getState().session.accessToken).toBeNull()
    expect(app.router.state.location.pathname).toBe(ROUTES.LOGIN)
  })

  it("shows the backend's message under each field it refused", async () => {
    server.use(
      http.post('/api/auth/login', () =>
        HttpResponse.json(
          {
            error: 'validation_error',
            message: 'Invalid request.',
            details: { email: ['Missing data for required field.'] },
          },
          { status: 400 },
        ),
      ),
    )
    const app = renderApp(ROUTES.LOGIN)

    await logInThroughForm(app.user, { email: 'x@example.com', password: 'anything1' })

    expect(await screen.findByLabelText('Email')).toHaveAccessibleDescription(
      'Missing data for required field.',
    )
  })

  it('returns to the page the visitor was sent from', async () => {
    const app = renderApp(`${ROUTES.LOGIN}?next=${encodeURIComponent('/events?page=2')}`)
    const { attendee } = MOCK_ACCOUNTS

    await logInThroughForm(app.user, attendee)

    await waitFor(() => expect(app.router.state.location.pathname).toBe(ROUTES.EVENTS))
    expect(app.router.state.location.search).toBe('?page=2')
  })

  it('offers sign-up to someone without an account', () => {
    renderApp(ROUTES.LOGIN)

    expect(screen.getByRole('link', { name: 'Create an account' })).toHaveAttribute(
      'href',
      ROUTES.SIGN_UP,
    )
  })

  it('sends someone already signed in to their landing view', async () => {
    const { router } = renderApp(ROUTES.LOGIN, { session: mockSessionFor(MOCK_ACCOUNTS.attendee) })

    await waitFor(() => expect(router.state.location.pathname).toBe(ROUTES.EVENTS))
  })
})
