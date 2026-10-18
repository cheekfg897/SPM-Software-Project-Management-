import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { ROLE } from '@/config/roles'
import { ROUTES } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import { MOCK_VENUES } from '@/mocks/handlers/venueFixtures'
import { server } from '@/mocks/server'
import { renderApp } from '@/test/render'

const STAFF_ACCOUNTS = [
  MOCK_ACCOUNTS.coordinator,
  MOCK_ACCOUNTS.lead,
  MOCK_ACCOUNTS.venueStaff,
  MOCK_ACCOUNTS.technicalSupport,
]
const COORDINATOR = mockSessionFor(MOCK_ACCOUNTS.coordinator)

function venueLinks(): (string | null)[] {
  const list = screen.getByRole('list', { name: 'Venues' })
  return within(list)
    .getAllByRole('link')
    .map((link) => link.getAttribute('href'))
}

describe('SCRUM-25 the venue list', () => {
  it('lists the venues in the order the backend sent, each with its location and capacity', async () => {
    const marina = MOCK_VENUES.marinaHall
    const marquee = MOCK_VENUES.lawnMarquee
    server.use(http.get('/api/venues', () => HttpResponse.json([marina, marquee])))
    renderApp(ROUTES.VENUES, { session: COORDINATOR })

    const marinaLink = await screen.findByRole('link', { name: /Marina Hall/ })

    expect(venueLinks()).toEqual(['/venues/1', '/venues/27'])
    expect(marinaLink).toHaveTextContent('Level 1, Marina Wing')
    expect(marinaLink).toHaveTextContent('Up to 200 people')
  })

  it('shows only what the backend lists, so a deactivated venue is not there', async () => {
    renderApp(ROUTES.VENUES, { session: COORDINATOR })

    await screen.findByRole('link', { name: /Boardroom Two/ })

    expect(venueLinks()).toEqual([
      '/venues/35',
      '/venues/2',
      '/venues/33',
      '/venues/31',
      '/venues/27',
      '/venues/1',
      '/venues/32',
    ])
    expect(screen.queryByText('Annexe Studio')).not.toBeInTheDocument()
  })

  it('opens a venue from its row', async () => {
    const { user, router } = renderApp(ROUTES.VENUES, { session: COORDINATOR })

    await user.click(await screen.findByRole('link', { name: /Lawn Marquee/ }))

    expect(router.state.location.pathname).toBe('/venues/27')
  })

  it('says it is loading, then says when there are no venues', async () => {
    server.use(http.get('/api/venues', () => HttpResponse.json([])))
    renderApp(ROUTES.VENUES, { session: COORDINATOR })

    expect(screen.getByRole('status')).toHaveTextContent('Loading venues…')
    expect(await screen.findByText('No venues are listed yet.')).toBeInTheDocument()
  })

  it('shows the backend message when the list cannot be read, and tries again', async () => {
    let calls = 0
    server.use(
      http.get('/api/venues', () => {
        calls += 1
        if (calls === 1) {
          return HttpResponse.json(
            { error: 'internal_error', message: 'Venues are unavailable.' },
            { status: 500 },
          )
        }
        return HttpResponse.json([MOCK_VENUES.boardroomTwo])
      }),
    )
    const { user } = renderApp(ROUTES.VENUES, { session: COORDINATOR })

    expect(await screen.findByRole('alert')).toHaveTextContent('Venues are unavailable.')
    await user.click(screen.getByRole('button', { name: 'Try again' }))

    expect(await screen.findByRole('link', { name: /Boardroom Two/ })).toBeInTheDocument()
  })
})

describe('SCRUM-25 who reaches the venue pages (ADR-0067)', () => {
  it.each(STAFF_ACCOUNTS.map((account) => [account.role, account] as const))(
    'gives %s a Venues link in the header that opens the list',
    async (_role, account) => {
      const { user, router } = renderApp(ROUTES.EVENTS, { session: mockSessionFor(account) })

      const nav = screen.getByRole('navigation', { name: 'Main' })
      await user.click(within(nav).getByRole('link', { name: 'Venues' }))

      expect(router.state.location.pathname).toBe(ROUTES.VENUES)
      expect(await screen.findByRole('heading', { level: 1, name: 'Venues' })).toBeInTheDocument()
    },
  )

  it.each([
    [ROLE.EVENT_ORGANISER, MOCK_ACCOUNTS.organiser, ROUTES.ORGANISER_HOME],
    [ROLE.ATTENDEE, MOCK_ACCOUNTS.attendee, ROUTES.MY_EVENTS],
  ])('gives %s no Venues link, and sends them home from the list', (_role, account, home) => {
    const { router } = renderApp(ROUTES.VENUES, { session: mockSessionFor(account) })

    expect(router.state.location.pathname).toBe(home)
    const nav = screen.getByRole('navigation', { name: 'Main' })
    expect(within(nav).queryByRole('link', { name: 'Venues' })).not.toBeInTheDocument()
  })

  it('sends someone signed out to the staff log-in, to come back to the list', () => {
    const { router } = renderApp(ROUTES.VENUES)

    expect(router.state.location.pathname).toBe(ROUTES.STAFF_LOGIN)
    expect(router.state.location.search).toBe(`?next=${encodeURIComponent(ROUTES.VENUES)}`)
  })
})
