import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { ROUTES } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import { INVALID_TOKEN_MESSAGE } from '@/mocks/responses'
import { server } from '@/mocks/server'
import { renderApp, renderWithProviders } from '@/test/render'

import { MyEventRequests } from './MyEventRequests'

/**
 * The organiser's event list on their home page (SCRUM-7 AC1, SCRUM-19 AC5, SCRUM-20 AC2,
 * SCRUM-24 AC1, AC8, AC10). The rows come from the mock in src/mocks/handlers/eventRequests.ts.
 */

const ORGANISER = mockSessionFor(MOCK_ACCOUNTS.organiser)

function openHome(session = ORGANISER) {
  return renderApp(ROUTES.ORGANISER_HOME, { session })
}

/** The list's row for the event with this name. */
async function rowFor(name: string): Promise<HTMLElement> {
  const heading = await screen.findByRole('heading', { name })
  const row = heading.closest('li')
  if (row === null) {
    throw new Error(`No list row holds "${name}"`)
  }
  return row
}

describe('SCRUM-19 organiser event list: starting a request', () => {
  it('offers a new event request from the list', async () => {
    openHome()

    expect(await screen.findByRole('link', { name: 'New event request' })).toHaveAttribute(
      'href',
      ROUTES.NEW_EVENT_REQUEST,
    )
  })
})

describe('SCRUM-7 organiser event list', () => {
  it('lists the requests in the order the backend sent them', async () => {
    openHome()

    const list = await screen.findByRole('list', { name: 'Your event requests' })
    const names = within(list)
      .getAllByRole('heading')
      .map((heading) => heading.textContent)
    // Newest request first, as sent: not by event date, which would put Annual Gala first.
    expect(names).toEqual([
      'Partner Summit',
      'Volunteer Thank-You Dinner',
      'Product Launch Night',
      'Leadership Offsite',
      'Customer Roadshow',
      'Annual Gala',
    ])
  })

  it('shows each request with its name, date, time, status and reference', async () => {
    openHome()

    const row = await rowFor('Partner Summit')
    expect(within(row).getByText('Thu, 12 Nov · 9:00 am – 5:00 pm')).toBeInTheDocument()
    expect(within(row).getByText('Under review')).toBeInTheDocument()
    expect(within(row).getByText(/EVR-7K2M9QXA/)).toBeInTheDocument()
    expect(within(row).getByText(/250 expected/)).toBeInTheDocument()
  })

  it('shows a submitted request as Submitted, with its reference', async () => {
    openHome()

    const row = await rowFor('Product Launch Night')
    expect(within(row).getByText('Submitted')).toBeInTheDocument()
    expect(within(row).getByText(/EVR-Q4ZT6N1B/)).toBeInTheDocument()
  })

  it('shows a draft as a draft, without a date yet', async () => {
    openHome()

    const row = await rowFor('Volunteer Thank-You Dinner')
    expect(within(row).getByText('Draft')).toBeInTheDocument()
    expect(within(row).getByText('Date to be set')).toBeInTheDocument()
    expect(within(row).queryByText(/expected/)).not.toBeInTheDocument()
  })

  it('shows both days of an event that runs over two', async () => {
    openHome()

    const row = await rowFor('Leadership Offsite')
    expect(within(row).getByText('Thu, 3 Dec, 10:00 am – Fri, 4 Dec, 4:00 pm')).toBeInTheDocument()
  })

  it("shows the backend's own message when there are no requests", async () => {
    // A message only the backend could have sent, so the page can't be showing its own.
    server.use(
      http.get('/api/events/requests', () =>
        HttpResponse.json({ event_requests: [], message: 'Nothing for Acme Events yet.' }),
      ),
    )
    openHome()

    expect(await screen.findByText('Nothing for Acme Events yet.')).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Your event requests' })).not.toBeInTheDocument()
  })

  it("shows the backend's message when the list is refused", async () => {
    openHome(mockSessionFor(MOCK_ACCOUNTS.unlinkedOrganiser))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Your account is not linked to a client organisation yet.',
    )
  })

  it("shows the backend's refusal when the session has gone", async () => {
    // The route only opens for a signed-in organiser, but a session can end while it's open.
    renderWithProviders(<MyEventRequests />)

    expect(await screen.findByRole('alert')).toHaveTextContent(INVALID_TOKEN_MESSAGE)
  })

  it('says it is loading until the list arrives', async () => {
    openHome()

    expect(screen.getByText('Loading your events…')).toBeInTheDocument()
    await screen.findByRole('list', { name: 'Your event requests' })
    expect(screen.queryByText('Loading your events…')).not.toBeInTheDocument()
  })

  it('still greets the organiser by name', async () => {
    openHome()

    expect(
      await screen.findByText(`Welcome back, ${MOCK_ACCOUNTS.organiser.full_name}.`),
    ).toBeInTheDocument()
  })
})
