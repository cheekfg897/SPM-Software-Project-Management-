import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { ROUTES } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import { MOCK_FAIR, MOCK_GALA } from '@/mocks/handlers/safetyFixtures'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

/**
 * SCRUM-97 AC5, AC6 and SCRUM-24 AC6, AC8, AC11: the Safety Officer's list of events awaiting
 * the safety check (docs/adr/0071).
 */

const LIST_URL = '/api/events/requests/awaiting-safety-review'
const OFFICER = mockSessionFor(MOCK_ACCOUNTS.safetyOfficer)
const GALA = MOCK_GALA.event.name
const FAIR = MOCK_FAIR.event.name
const TOWN_HALL = 'Year-End Town Hall'

function renderList() {
  return renderApp(ROUTES.SAFETY_REVIEW, { session: OFFICER })
}

/** An event's card, found by the name its heading gives it. */
async function findEvent(name: string) {
  return within(await screen.findByRole('article', { name }))
}

function listReads(requests: Request[]) {
  return requests.filter(
    (request) => request.method === 'GET' && new URL(request.url).pathname === LIST_URL,
  )
}

describe('SCRUM-97 and SCRUM-24 AC6 the Safety Officer list', () => {
  it('lists the events awaiting the safety check soonest first, in the order the backend sent', async () => {
    renderList()

    expect(screen.getByRole('status')).toHaveTextContent('Loading events awaiting the safety check')
    await findEvent(FAIR)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(
      screen.getAllByRole('heading', { level: 2 }).map((heading) => heading.textContent),
    ).toEqual([FAIR, TOWN_HALL, GALA])
  })

  it("shows each event's name, reference, date, time, status, attendance and accessibility needs", async () => {
    renderList()

    const gala = await findEvent(GALA)
    expect(gala.getByText('EVR-SAFE0002')).toBeInTheDocument()
    expect(gala.getByText('Fri, 4 Dec · 6:00 pm – 11:00 pm')).toBeInTheDocument()
    expect(gala.getByText('Safety review')).toBeInTheDocument()
    expect(gala.getByText('400')).toBeInTheDocument()
    expect(gala.getByText('Wheelchair seating for six guests')).toBeInTheDocument()
    const fair = await findEvent(FAIR)
    expect(fair.getByText('Sat, 21 Nov · 9:00 am – 4:00 pm')).toBeInTheDocument()
    expect(fair.getByText('250')).toBeInTheDocument()
    expect(fair.getByText('None given')).toBeInTheDocument()
  })

  it("shows each booked venue's capacity, layouts, facilities, accessibility features and booked period", async () => {
    renderList()

    const venue = within((await findEvent(GALA)).getByRole('listitem', { name: 'Marina Ballroom' }))
    expect(venue.getByText('4 Dec, 5:00 pm – 11:30 pm')).toBeInTheDocument()
    expect(venue.getByText('500')).toBeInTheDocument()
    expect(venue.getByText('Banquet, Theatre')).toBeInTheDocument()
    expect(venue.getByText('stage, pa system')).toBeInTheDocument()
    expect(venue.getByText('wheelchair access, hearing loop')).toBeInTheDocument()
    const fairVenue = within((await findEvent(FAIR)).getByRole('listitem', { name: 'Atrium Hall' }))
    expect(fairVenue.getByText('Exhibition')).toBeInTheDocument()
    expect(fairVenue.getAllByText('None listed')).toHaveLength(2)
  })

  it("shows each equipment request with its quantity, notes and Technical Support's outcome", async () => {
    renderList()

    const gala = await findEvent(GALA)
    const projector = within(gala.getByRole('listitem', { name: 'Projector' }))
    expect(projector.getByText('2 requested')).toBeInTheDocument()
    expect(projector.getByText('Ceiling mount')).toBeInTheDocument()
    expect(projector.getByText('Fulfilled, 2 provided')).toBeInTheDocument()
    const microphones = within(gala.getByRole('listitem', { name: 'Wireless microphone' }))
    expect(microphones.getByText('6 requested')).toBeInTheDocument()
    expect(microphones.getByText('Partially fulfilled, 4 provided')).toBeInTheDocument()
    expect(microphones.getByText('Only four in stock that week.')).toBeInTheDocument()
    const lectern = within((await findEvent(TOWN_HALL)).getByRole('listitem', { name: 'Lectern' }))
    expect(lectern.getByText('Unavailable, 0 provided')).toBeInTheDocument()
    expect((await findEvent(FAIR)).getByText('No equipment requested.')).toBeInTheDocument()
  })

  it('says so when an event has no venue booked', async () => {
    server.use(
      http.get(LIST_URL, () =>
        HttpResponse.json({ events: [{ event: MOCK_FAIR.event, venues: [], equipment: [] }] }),
      ),
    )
    renderList()

    expect((await findEvent(FAIR)).getByText('No venue booked.')).toBeInTheDocument()
  })

  it('shows a layout or an equipment request it has no words for as the backend sent it', async () => {
    const venue = { ...MOCK_FAIR.venues[0], layouts: ['amphitheatre'] }
    const equipment = {
      equipment_type_name: 'Stage riser',
      quantity: 3,
      notes: null,
      status: 'requested',
      provided_quantity: null,
      outcome_note: null,
    }
    server.use(
      http.get(LIST_URL, () =>
        HttpResponse.json({
          events: [{ event: MOCK_FAIR.event, venues: [venue], equipment: [equipment] }],
        }),
      ),
    )
    renderList()

    const fair = await findEvent(FAIR)
    expect(fair.getByText('amphitheatre')).toBeInTheDocument()
    expect(
      within(fair.getByRole('listitem', { name: 'Stage riser' })).getByText('Requested'),
    ).toBeInTheDocument()
  })

  it("shows the backend's message instead of a list when no event is waiting", async () => {
    server.use(
      http.get(LIST_URL, () =>
        HttpResponse.json({ events: [], message: 'Nothing for the Safety Officer today.' }),
      ),
    )
    renderList()

    expect(await screen.findByText('Nothing for the Safety Officer today.')).toBeInTheDocument()
    expect(screen.queryByRole('article')).not.toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it("shows the backend's message when the list cannot be read, and reads it again on Try again", async () => {
    server.use(
      http.get(
        LIST_URL,
        () =>
          HttpResponse.json(
            { error: 'server_error', message: 'Something went wrong.' },
            { status: 500 },
          ),
        { once: true },
      ),
    )
    const { user } = renderList()

    expect(await screen.findByRole('alert')).toHaveTextContent('Something went wrong.')
    await user.click(screen.getByRole('button', { name: 'Try again' }))

    expect(await screen.findByRole('article', { name: GALA })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it.each([
    ['an Event Coordinator', MOCK_ACCOUNTS.coordinator],
    ['Venue Staff', MOCK_ACCOUNTS.venueStaff],
  ])('sends %s to the staff home without asking for the list', async (_who, account) => {
    const requests = recordRequests()
    const { router } = renderApp(ROUTES.SAFETY_REVIEW, { session: mockSessionFor(account) })

    await waitFor(() => expect(router.state.location.pathname).toBe(ROUTES.STAFF_HOME))
    expect(listReads(requests)).toHaveLength(0)
  })

  it('sends a visitor to the staff log-in page', async () => {
    const { router } = renderApp(ROUTES.SAFETY_REVIEW)

    await waitFor(() => expect(router.state.location.pathname).toBe(ROUTES.STAFF_LOGIN))
  })

  it('links the Safety Officer to the list from the header', () => {
    renderApp(ROUTES.EVENTS, { session: OFFICER })

    const header = within(screen.getByRole('banner'))
    expect(header.getByRole('link', { name: 'Safety review' })).toHaveAttribute(
      'href',
      ROUTES.SAFETY_REVIEW,
    )
  })

  it.each([
    ['an Event Coordinator', MOCK_ACCOUNTS.coordinator],
    ['an Attendee', MOCK_ACCOUNTS.attendee],
  ])('shows %s no link to the safety list', (_who, account) => {
    renderApp(ROUTES.EVENTS, { session: mockSessionFor(account) })

    expect(
      within(screen.getByRole('banner')).queryByRole('link', { name: 'Safety review' }),
    ).not.toBeInTheDocument()
  })
})
