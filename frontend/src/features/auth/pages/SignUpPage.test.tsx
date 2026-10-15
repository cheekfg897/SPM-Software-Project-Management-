import { screen, waitFor } from '@testing-library/react'

import { ROUTES } from '@/config/routes'
import { EMAIL_IN_USE_MESSAGE, MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/handlers/auth'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

type AppRender = ReturnType<typeof renderApp>

const NEW_ATTENDEE = {
  full_name: 'Priya Nair',
  email: 'priya@example.com',
  password: 'Password123',
}

async function fillIn({ user }: AppRender, details: typeof NEW_ATTENDEE) {
  await user.type(screen.getByLabelText('Full name'), details.full_name)
  await user.type(screen.getByLabelText('Email'), details.email)
  await user.type(screen.getByLabelText('Password'), details.password)
}

async function submit({ user }: AppRender) {
  await user.click(screen.getByRole('button', { name: 'Create account' }))
}

/** The JSON bodies of the sign-up requests among `requests` (from recordRequests). */
async function registrationBodies(requests: Request[]): Promise<unknown[]> {
  const registrations = requests.filter((request) => request.url.endsWith('/api/auth/register'))
  return Promise.all(registrations.map((request): Promise<unknown> => request.json()))
}

describe('SCRUM-65 sign up', () => {
  it('creates an attendee account, signs them in and takes them to their own events', async () => {
    const app = renderApp(ROUTES.SIGN_UP)

    await fillIn(app, NEW_ATTENDEE)
    await submit(app)

    await waitFor(() => expect(app.router.state.location.pathname).toBe(ROUTES.MY_EVENTS))
    expect(app.store.getState().session.user?.full_name).toBe(NEW_ATTENDEE.full_name)
  })

  it('sends no organisation for an attendee', async () => {
    const requests = recordRequests()
    const app = renderApp(ROUTES.SIGN_UP)

    expect(screen.queryByLabelText('Organisation ID')).not.toBeInTheDocument()
    await fillIn(app, NEW_ATTENDEE)
    await submit(app)

    await waitFor(() => expect(app.router.state.location.pathname).toBe(ROUTES.MY_EVENTS))
    expect(await registrationBodies(requests)).toEqual([{ ...NEW_ATTENDEE, role: 'attendee' }])
  })

  it('asks an organiser for the organisation ID staff gave them, and sends it as a number', async () => {
    const requests = recordRequests()
    const app = renderApp(ROUTES.SIGN_UP)

    await app.user.click(screen.getByRole('radio', { name: /Organise events/ }))
    const organisationField = screen.getByLabelText('Organisation ID')
    expect(organisationField).toHaveAccessibleDescription(/ConnectSphere staff/)
    await fillIn(app, NEW_ATTENDEE)
    await app.user.type(organisationField, '1')
    await submit(app)

    expect(await screen.findByText(`Welcome back, ${NEW_ATTENDEE.full_name}.`)).toBeInTheDocument()
    expect(app.router.state.location.pathname).toBe(ROUTES.ORGANISER_HOME)
    expect(await registrationBodies(requests)).toEqual([
      { ...NEW_ATTENDEE, role: 'event_organiser', organisation_id: 1 },
    ])
  })

  it("shows the backend's message when an organiser leaves the organisation out", async () => {
    const app = renderApp(ROUTES.SIGN_UP)

    await app.user.click(screen.getByRole('radio', { name: /Organise events/ }))
    await fillIn(app, NEW_ATTENDEE)
    await submit(app)

    expect(await screen.findByLabelText('Organisation ID')).toHaveAccessibleDescription(
      'Event Organisers must belong to a client organisation.',
    )
  })

  it('refuses an email already in use', async () => {
    const app = renderApp(ROUTES.SIGN_UP)

    await fillIn(app, { ...NEW_ATTENDEE, email: MOCK_ACCOUNTS.attendee.email })
    await submit(app)

    expect(await screen.findByRole('alert')).toHaveTextContent(EMAIL_IN_USE_MESSAGE)
    expect(app.store.getState().session.accessToken).toBeNull()
  })

  it("shows the backend's password rule under the password", async () => {
    const app = renderApp(ROUTES.SIGN_UP)

    await fillIn(app, { ...NEW_ATTENDEE, password: 'short1' })
    await submit(app)

    expect(await screen.findByLabelText('Password')).toHaveAccessibleDescription(
      'Password must be at least 8 characters long.',
    )
  })

  it('offers log-in to someone who already has an account', () => {
    renderApp(ROUTES.SIGN_UP)

    expect(screen.getByRole('link', { name: 'Log in instead' })).toHaveAttribute(
      'href',
      ROUTES.LOGIN,
    )
  })

  it('sends someone already signed in to their landing view', async () => {
    const { router } = renderApp(ROUTES.SIGN_UP, {
      session: mockSessionFor(MOCK_ACCOUNTS.organiser),
    })

    await screen.findByRole('heading', { name: 'Your events' })
    expect(router.state.location.pathname).toBe(ROUTES.ORGANISER_HOME)
  })
})
