import { act, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { ROUTES } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/handlers/auth'
import { server } from '@/mocks/server'
import { signedIn } from '@/store'
import { renderApp } from '@/test/render'

import { CATALOGUE_URL } from '../test/catalogueResponses'

const ATTENDEE_SESSION = mockSessionFor(MOCK_ACCOUNTS.attendee)
const ORGANISER_SESSION = mockSessionFor(MOCK_ACCOUNTS.organiser)

async function findCard(name: string): Promise<HTMLElement> {
  const heading = await screen.findByRole('heading', { name })
  const card = heading.closest('article')
  if (card === null) {
    throw new Error(`${name} is not inside an article.`)
  }
  return card
}

describe('SCRUM-52 registering from the catalogue', () => {
  it('sends a visitor to log in, and back to the same results afterwards', async () => {
    const { user, router } = renderApp(`${ROUTES.EVENTS}?q=jazz`)

    await user.click(
      within(await findCard('Jazz by the Bay')).getByRole('button', { name: 'Register' }),
    )

    expect(router.state.location.pathname).toBe(ROUTES.LOGIN)
    expect(router.state.location.search).toBe(`?next=${encodeURIComponent('/events?q=jazz')}`)
  })

  it("registers an attendee, then shows the backend's updated place", async () => {
    const { user } = renderApp(ROUTES.EVENTS, { session: ATTENDEE_SESSION })
    const card = await findCard('Jazz by the Bay')
    expect(within(card).getByText('12 places left')).toBeInTheDocument()

    await user.click(within(card).getByRole('button', { name: 'Register' }))

    expect(await within(card).findByText("You're registered")).toBeInTheDocument()
    expect(within(card).queryByRole('button', { name: 'Register' })).not.toBeInTheDocument()
  })

  it('is busy while the registration is being sent', async () => {
    server.use(
      http.post(
        `${CATALOGUE_URL}/:eventId/registrations`,
        () => new Promise<never>(() => undefined),
      ),
    )
    const { user } = renderApp(ROUTES.EVENTS, { session: ATTENDEE_SESSION })
    const card = await findCard('Jazz by the Bay')

    await user.click(within(card).getByRole('button', { name: 'Register' }))

    expect(within(card).getByRole('button', { name: 'Register' })).toHaveAttribute(
      'aria-busy',
      'true',
    )
  })

  it("shows the backend's refusal on that event's card only", async () => {
    server.use(
      http.post(`${CATALOGUE_URL}/:eventId/registrations`, () =>
        HttpResponse.json({ error: 'event_full', message: 'This event is full.' }, { status: 409 }),
      ),
    )
    const { user } = renderApp(ROUTES.EVENTS, { session: ATTENDEE_SESSION })
    const card = await findCard('Jazz by the Bay')

    await user.click(within(card).getByRole('button', { name: 'Register' }))

    expect(await within(card).findByRole('alert')).toHaveTextContent('This event is full.')
    expect(within(await findCard('Data Viz Meetup')).queryByRole('alert')).not.toBeInTheDocument()
  })

  it('offers nothing to register for on a full event or one already held', async () => {
    renderApp(ROUTES.EVENTS, { session: ATTENDEE_SESSION })

    const full = await findCard('Night Market Photography Walk')
    const held = await findCard('Startup Pitch Night')
    expect(within(full).queryByRole('button', { name: 'Register' })).not.toBeInTheDocument()
    expect(within(held).getByText("You're registered")).toBeInTheDocument()
    expect(within(held).queryByRole('button', { name: 'Register' })).not.toBeInTheDocument()
  })

  it('shows no Register button to a signed-in user who is not an attendee (SCRUM-21)', async () => {
    renderApp(ROUTES.EVENTS, { session: ORGANISER_SESSION })

    await findCard('Jazz by the Bay')
    await waitFor(() => expect(screen.queryAllByRole('button', { name: 'Register' })).toEqual([]))
  })

  it('reads the catalogue again for whoever signs in, so their registrations show', async () => {
    const { store } = renderApp(ROUTES.EVENTS)
    const card = await findCard('Startup Pitch Night')
    expect(within(card).queryByText("You're registered")).not.toBeInTheDocument()

    act(() => {
      store.dispatch(signedIn(ATTENDEE_SESSION))
    })

    expect(await within(card).findByText("You're registered")).toBeInTheDocument()
  })
})
