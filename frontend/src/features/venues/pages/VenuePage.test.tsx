import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { venuePath } from '@/config/routes'
import type { Venue } from '@/features/venues/api'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import { MOCK_VENUES } from '@/mocks/handlers/venueFixtures'
import { server } from '@/mocks/server'
import { renderApp } from '@/test/render'

const COORDINATOR = mockSessionFor(MOCK_ACCOUNTS.coordinator)
/** An id no fixture uses, so the page can only show it if it asked for this venue. */
const OWN_VENUE_ID = 731

/** A venue only this test's backend knows, with every field set to something no default has. */
const RIVERSIDE: Venue = {
  id: OWN_VENUE_ID,
  name: 'Riverside Loft',
  location: 'Pier 7',
  capacity: 85,
  facilities: ['piano', 'bar counter'],
  accessibility_features: ['braille signage'],
  supported_layouts: ['exhibition', 'classroom'],
  opening_hours: [
    { open: { day: 'wednesday', time: '07:30' }, close: { day: 'wednesday', time: '11:00' } },
    { open: { day: 'friday', time: '19:00' }, close: { day: 'saturday', time: '01:15' } },
  ],
  setup_minutes: 25,
  turnaround_minutes: 1,
  is_active: true,
}

function serveVenue(venue: Venue) {
  server.use(http.get(`/api/venues/${venue.id}`, () => HttpResponse.json(venue)))
}

/** The value next to a term in the venue's details. */
function detail(term: string) {
  const details = screen.getByRole('region', { name: 'Details' })
  const termElement = within(details).getByText(term, { selector: 'dt' })
  return termElement.nextElementSibling
}

describe('SCRUM-25 a venue page', () => {
  it('shows every detail the backend holds for the venue', async () => {
    serveVenue(RIVERSIDE)
    renderApp(venuePath(OWN_VENUE_ID), { session: COORDINATOR })

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Riverside Loft' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Pier 7')).toBeInTheDocument()
    expect(detail('Capacity')).toHaveTextContent('Up to 85 people')
    expect(detail('Layouts')).toHaveTextContent('Exhibition, Classroom')
    expect(detail('Facilities')).toHaveTextContent('piano, bar counter')
    expect(detail('Accessibility')).toHaveTextContent('braille signage')
  })

  it('shows the opening hours in the order the backend sent, overnight ones with their close day', async () => {
    serveVenue(RIVERSIDE)
    renderApp(venuePath(OWN_VENUE_ID), { session: COORDINATOR })

    const hours = await screen.findByRole('region', { name: 'Opening hours' })
    const rows = within(hours)
      .getAllByRole('listitem')
      .map((row) => row.textContent)

    expect(rows).toEqual(['Wednesday7:30 am – 11:00 am', 'Friday7:00 pm – Saturday 1:15 am'])
  })

  it('shows the setup and turnaround time the venue needs (SCRUM-67)', async () => {
    serveVenue(RIVERSIDE)
    renderApp(venuePath(OWN_VENUE_ID), { session: COORDINATOR })

    const buffers = await screen.findByRole('region', { name: 'Setup and turnaround' })

    expect(
      within(buffers).getByText('Setup', { selector: 'dt' }).nextElementSibling,
    ).toHaveTextContent('25 minutes')
    expect(
      within(buffers).getByText('Turnaround', { selector: 'dt' }).nextElementSibling,
    ).toHaveTextContent('1 minute')
  })

  it('says when a list is empty and when the venue is closed all week', async () => {
    serveVenue({
      ...RIVERSIDE,
      facilities: [],
      accessibility_features: [],
      supported_layouts: [],
      opening_hours: [],
    })
    renderApp(venuePath(OWN_VENUE_ID), { session: COORDINATOR })

    await screen.findByRole('heading', { level: 1, name: 'Riverside Loft' })

    expect(detail('Layouts')).toHaveTextContent('None listed')
    expect(detail('Facilities')).toHaveTextContent('None listed')
    expect(detail('Accessibility')).toHaveTextContent('None listed')
    const hours = screen.getByRole('region', { name: 'Opening hours' })
    expect(hours).toHaveTextContent('Closed all week')
  })

  it('says a deactivated venue is deactivated, and an active one is not', async () => {
    serveVenue({ ...RIVERSIDE, is_active: false })
    renderApp(venuePath(OWN_VENUE_ID), { session: COORDINATOR })

    expect(await screen.findByText(/This venue is deactivated/)).toBeInTheDocument()
  })

  it('does not call an active venue deactivated', async () => {
    renderApp(venuePath(MOCK_VENUES.marinaHall.id), { session: COORDINATOR })

    await screen.findByRole('heading', { level: 1, name: 'Marina Hall' })

    expect(screen.queryByText(/deactivated/)).not.toBeInTheDocument()
  })

  it.each([
    { account: MOCK_ACCOUNTS.organiser, home: '/organiser' },
    { account: MOCK_ACCOUNTS.attendee, home: '/my-events' },
  ])('sends $account.role home rather than show them a venue (ADR-0053)', ({ account, home }) => {
    const { router } = renderApp('/venues/1', { session: mockSessionFor(account) })

    expect(router.state.location.pathname).toBe(home)
  })

  it('says it is loading, then shows the backend message for a venue that does not exist', async () => {
    renderApp(venuePath(4242), { session: COORDINATOR })

    expect(screen.getByRole('status')).toHaveTextContent('Loading the venue…')
    expect(await screen.findByRole('alert')).toHaveTextContent('Venue not found.')
  })
})
