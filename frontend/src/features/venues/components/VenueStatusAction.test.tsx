import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

const VENUE_STAFF = mockSessionFor(MOCK_ACCOUNTS.venueStaff)
/** Lawn Marquee (active) and Annexe Studio (deactivated), written out. */
const MARQUEE_PAGE = '/venues/27'
const ANNEXE_PAGE = '/venues/38'
const DEACTIVATED_NOTICE = /This venue is deactivated/

/** Go to the venue list from the header and return it, once its rows are there. */
async function openTheList(user: ReturnType<typeof renderApp>['user']) {
  const nav = screen.getByRole('navigation', { name: 'Main' })
  await user.click(within(nav).getByRole('link', { name: 'Venues' }))
  return within(await screen.findByRole('list', { name: 'Venues' }))
}

describe('SCRUM-25 deactivating a venue (AC5)', () => {
  it('deactivates the venue, which then says so and leaves the list', async () => {
    const requests = recordRequests()
    const { user } = renderApp(MARQUEE_PAGE, { session: VENUE_STAFF })

    await user.click(await screen.findByRole('button', { name: 'Deactivate venue' }))

    expect(await screen.findByText(DEACTIVATED_NOTICE)).toBeInTheDocument()
    const sent = requests.find((request) => request.method === 'POST')
    expect(new URL(sent?.url ?? '').pathname).toBe('/api/venues/27/deactivate')
    expect(screen.getByRole('button', { name: 'Reactivate venue' })).toBeInTheDocument()
    const list = await openTheList(user)
    expect(list.getByRole('link', { name: /Marina Hall/ })).toBeInTheDocument()
    expect(list.queryByRole('link', { name: /Lawn Marquee/ })).not.toBeInTheDocument()
  })

  it('says what deactivating does before it is done', async () => {
    renderApp(MARQUEE_PAGE, { session: VENUE_STAFF })

    const section = await screen.findByRole('region', { name: 'Deactivate venue' })

    expect(section).toHaveTextContent(
      'It leaves the venue list and venue search. Bookings already made for it keep it.',
    )
  })

  it('shows the backend message when it is refused', async () => {
    server.use(
      http.post('/api/venues/27/deactivate', () =>
        HttpResponse.json(
          { error: 'conflict', message: 'This venue cannot be deactivated now.' },
          { status: 409 },
        ),
      ),
    )
    const { user } = renderApp(MARQUEE_PAGE, { session: VENUE_STAFF })

    await user.click(await screen.findByRole('button', { name: 'Deactivate venue' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This venue cannot be deactivated now.',
    )
    expect(screen.queryByText(DEACTIVATED_NOTICE)).not.toBeInTheDocument()
  })
})

describe('SCRUM-25 reactivating a venue (AC6)', () => {
  it('reactivates a deactivated venue, which comes back to the list', async () => {
    const requests = recordRequests()
    const { user } = renderApp(ANNEXE_PAGE, { session: VENUE_STAFF })
    await screen.findByText(DEACTIVATED_NOTICE)

    await user.click(screen.getByRole('button', { name: 'Reactivate venue' }))

    expect(await screen.findByRole('button', { name: 'Deactivate venue' })).toBeInTheDocument()
    expect(screen.queryByText(DEACTIVATED_NOTICE)).not.toBeInTheDocument()
    const sent = requests.find((request) => request.method === 'POST')
    expect(new URL(sent?.url ?? '').pathname).toBe('/api/venues/38/reactivate')
    const list = await openTheList(user)
    expect(list.getByRole('link', { name: /Annexe Studio/ })).toBeInTheDocument()
  })
})

describe('SCRUM-25 only Venue Staff deactivate or reactivate (AC4)', () => {
  it.each([MOCK_ACCOUNTS.coordinator, MOCK_ACCOUNTS.lead, MOCK_ACCOUNTS.technicalSupport])(
    'offers $full_name neither',
    async (account) => {
      renderApp(ANNEXE_PAGE, { session: mockSessionFor(account) })
      await screen.findByText(DEACTIVATED_NOTICE)

      expect(screen.queryByRole('button', { name: 'Reactivate venue' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Deactivate venue' })).not.toBeInTheDocument()
    },
  )
})
