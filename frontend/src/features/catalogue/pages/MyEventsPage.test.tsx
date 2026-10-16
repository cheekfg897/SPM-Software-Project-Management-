import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { ROUTES } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import { server } from '@/mocks/server'
import { renderApp } from '@/test/render'
import { signedIn } from '@/store'

/**
 * The Attendee's own events (SCRUM-24 AC7, SCRUM-52 AC5, docs/adr/0044). The mock backend's
 * "now" is Monday 5 Oct 2026, midday. The mock attendee holds Startup Pitch Night (7 Oct) and
 * a run since cancelled (10 Oct) ahead, and this morning's yoga and a completed show behind.
 */

const ATTENDEE = mockSessionFor(MOCK_ACCOUNTS.attendee)
const FRESH_ATTENDEE = mockSessionFor(MOCK_ACCOUNTS.freshAttendee)
const MY_EVENTS_API = '/api/events/registrations'

/** The event names on the page, top to bottom. */
function eventNames(): string[] {
  return screen.getAllByRole('heading', { level: 3 }).map((heading) => heading.textContent)
}

function eventCard(name: string): HTMLElement {
  const card = screen.getByRole('heading', { name }).closest('article')
  if (card === null) {
    throw new Error(`${name} is not inside an article.`)
  }
  return card
}

describe('SCRUM-24 my events page: upcoming and past', () => {
  it('shows upcoming events by default, by day, each with its time and status', async () => {
    renderApp(ROUTES.MY_EVENTS, { session: ATTENDEE })

    expect(await screen.findByRole('heading', { name: 'Startup Pitch Night' })).toBeInTheDocument()
    expect(eventNames()).toEqual(['Startup Pitch Night', 'Harbour Lights Run'])
    expect(screen.getByRole('heading', { name: 'Wednesday 7 Oct' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Saturday 10 Oct' })).toBeInTheDocument()
    const pitchNight = within(eventCard('Startup Pitch Night'))
    expect(pitchNight.getByText('7:00 pm – 9:30 pm')).toBeInTheDocument()
    expect(pitchNight.getByText('Confirmed')).toBeInTheDocument()
    expect(within(eventCard('Harbour Lights Run')).getByText('Cancelled')).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Upcoming' })).toBeChecked()
  })

  it('shows past events, most recent first, once Past is chosen, and keeps it in the URL', async () => {
    const { user, router } = renderApp(ROUTES.MY_EVENTS, { session: ATTENDEE })
    await screen.findByRole('heading', { name: 'Startup Pitch Night' })

    await user.click(screen.getByRole('radio', { name: 'Past' }))

    expect(
      await screen.findByRole('heading', { name: 'Orchid Show Opening Night' }),
    ).toBeInTheDocument()
    expect(eventNames()).toEqual(['Sunrise Yoga on the Lawn', 'Orchid Show Opening Night'])
    expect(
      within(eventCard('Orchid Show Opening Night')).getByText('Completed'),
    ).toBeInTheDocument()
    expect(router.state.location.search).toBe('?when=past')
  })

  it('opens on the past events from a link to them', async () => {
    renderApp(`${ROUTES.MY_EVENTS}?when=past`, { session: ATTENDEE })

    expect(
      await screen.findByRole('heading', { name: 'Orchid Show Opening Night' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Past' })).toBeChecked()
  })

  it('takes the window out of the URL on going back to Upcoming, the backend default', async () => {
    const { user, router } = renderApp(`${ROUTES.MY_EVENTS}?when=past`, { session: ATTENDEE })
    await screen.findByRole('heading', { name: 'Orchid Show Opening Night' })

    await user.click(screen.getByRole('radio', { name: 'Upcoming' }))

    expect(await screen.findByRole('heading', { name: 'Startup Pitch Night' })).toBeInTheDocument()
    expect(router.state.location.search).toBe('')
  })
})

describe('SCRUM-24 my events page: none, loading and errors', () => {
  it("shows the backend's message and a way to find events when there are none", async () => {
    renderApp(ROUTES.MY_EVENTS, { session: FRESH_ATTENDEE })

    expect(await screen.findByText('You have no upcoming events.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Browse events' })).toHaveAttribute(
      'href',
      ROUTES.EVENTS,
    )
  })

  it("shows the backend's message and a way to find events when there are no past ones", async () => {
    // A fresh attendee holds nothing, so both halves are empty. Opening on Past checks the
    // message comes from the half that was asked for, not a fixed "upcoming" line.
    renderApp(`${ROUTES.MY_EVENTS}?when=past`, { session: FRESH_ATTENDEE })

    expect(await screen.findByText('You have no past events.')).toBeInTheDocument()
    expect(screen.queryByText('You have no upcoming events.')).not.toBeInTheDocument()
    // An empty list is a message, not a blank page (SCRUM-24 AC11), and it points somewhere.
    expect(screen.getByRole('link', { name: 'Browse events' })).toHaveAttribute(
      'href',
      ROUTES.EVENTS,
    )
    expect(screen.getByRole('radio', { name: 'Past' })).toBeChecked()
  })

  it('says it is loading until the backend answers', () => {
    renderApp(ROUTES.MY_EVENTS, { session: ATTENDEE })

    expect(screen.getByRole('status')).toHaveTextContent('Loading your events…')
  })

  it("shows the backend's error when the list can't be read", async () => {
    server.use(
      http.get(MY_EVENTS_API, () =>
        HttpResponse.json(
          { error: 'internal_error', message: 'Something went wrong on our side.' },
          { status: 500 },
        ),
      ),
    )

    renderApp(ROUTES.MY_EVENTS, { session: ATTENDEE })

    expect(await screen.findByRole('alert')).toHaveTextContent('Something went wrong on our side.')
  })

  it("reads the list again for the next person to sign in, never showing the last one's", async () => {
    const { store } = renderApp(ROUTES.MY_EVENTS, { session: ATTENDEE })
    await screen.findByRole('heading', { name: 'Startup Pitch Night' })

    store.dispatch(signedIn(FRESH_ATTENDEE))

    expect(await screen.findByText('You have no upcoming events.')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Startup Pitch Night' })).not.toBeInTheDocument()
  })
})

describe('SCRUM-24 my events page: who may open it', () => {
  it('sends a visitor to log in, and back here afterwards', () => {
    const { router } = renderApp(ROUTES.MY_EVENTS)

    expect(router.state.location.pathname).toBe(ROUTES.LOGIN)
    expect(router.state.location.search).toContain(encodeURIComponent(ROUTES.MY_EVENTS))
  })

  it('sends an organiser to their own home', () => {
    const { router } = renderApp(ROUTES.MY_EVENTS, {
      session: mockSessionFor(MOCK_ACCOUNTS.organiser),
    })

    expect(router.state.location.pathname).toBe(ROUTES.ORGANISER_HOME)
  })
})

describe('SCRUM-52 my events page: after registering', () => {
  it('lists an event the attendee has just registered for', async () => {
    const { user, router } = renderApp(ROUTES.MY_EVENTS, { session: ATTENDEE })
    await screen.findByRole('heading', { name: 'Startup Pitch Night' })

    await router.navigate(ROUTES.EVENTS)
    await screen.findByRole('heading', { name: 'Jazz by the Bay' })
    await user.click(within(eventCard('Jazz by the Bay')).getByRole('button', { name: 'Register' }))
    expect(
      await within(eventCard('Jazz by the Bay')).findByText("You're registered"),
    ).toBeInTheDocument()
    await router.navigate(ROUTES.MY_EVENTS)
    // Wait for this page first: until it renders, the catalogue's own Jazz by the Bay card
    // can still be on screen, and finding that one fails once it is removed.
    await screen.findByRole('heading', { level: 1, name: 'My events' })

    expect(await screen.findByRole('heading', { name: 'Jazz by the Bay' })).toBeInTheDocument()
  })
})
