import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { ROUTES } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import { validationError } from '@/mocks/responses'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

import { fill, search, SEARCH_URL, searchesSent, typeInto } from '../test/searchForm'

const COORDINATOR = { session: mockSessionFor(MOCK_ACCOUNTS.coordinator) }
/**
 * 20 November, 09:00 to 17:00, for 120 people: the Garden Pavilion, Harbourfront Hall, Lawn
 * Marquee and Marina Hall fit.
 */
const SEARCHED_PATH = `${ROUTES.VENUE_SEARCH}?date=2026-11-20&start=09:00&end=17:00&min_capacity=120`

function resultsList(): HTMLElement {
  return screen.getByRole('list', { name: 'Venues that match' })
}

describe('SCRUM-35 venue search page', () => {
  it('offers every filter the backend takes, and searches nothing until asked', async () => {
    const requests = recordRequests()

    renderApp(ROUTES.VENUE_SEARCH, COORDINATOR)

    await screen.findByRole('heading', { level: 1, name: 'Find a venue' })
    for (const label of [
      'Date',
      'Start time',
      'End time',
      'End date',
      'Minimum capacity',
      'Location',
      'Room layout',
      'Facilities',
      'Accessibility requirements',
    ]) {
      expect(screen.getByLabelText(label)).toBeInTheDocument()
    }
    expect(searchesSent(requests)).toHaveLength(0)
    expect(screen.queryByRole('heading', { name: 'Venues that match' })).not.toBeInTheDocument()
  })

  it('sends the filters in business time, one requirement per line, and keeps them in the URL', async () => {
    const requests = recordRequests()
    const view = renderApp(ROUTES.VENUE_SEARCH, COORDINATOR)

    await fill(view, {
      Location: 'Marina',
      Facilities: 'Projector{Enter}{Enter}stage',
      'Accessibility requirements': 'step-free access',
    })
    await view.user.selectOptions(screen.getByLabelText('Room layout'), 'Theatre')
    await view.user.click(screen.getByRole('button', { name: 'Search venues' }))

    await screen.findByRole('article', { name: 'Harbourfront Hall' })
    const sent = searchesSent(requests)
    expect(sent).toHaveLength(1)
    expect(await sent[0]?.json()).toEqual({
      start_time: '2026-11-20T09:00:00+08:00',
      end_time: '2026-11-20T17:00:00+08:00',
      min_capacity: 120,
      location: 'Marina',
      required_layout: 'theatre',
      required_facilities: ['Projector', 'stage'],
      required_accessibility: ['step-free access'],
    })
    const params = view.router.state.location.search
    expect(params).toContain('location=Marina')
    expect(params).toContain('required_facilities=Projector&required_facilities=stage')
  })

  it('sends an overnight period ending on the end date', async () => {
    const requests = recordRequests()
    const view = renderApp(ROUTES.VENUE_SEARCH, COORDINATOR)

    await search(view, { 'End time': '01:00', 'End date': '2026-11-21' })

    await screen.findByRole('article', { name: 'Harbourfront Hall' })
    const sent = (await searchesSent(requests).at(-1)?.json()) as Record<string, unknown>
    expect(sent.end_time).toBe('2026-11-21T01:00:00+08:00')
  })

  it("shows each venue's name, capacity, location, id and the requirements it meets, in the backend's order", async () => {
    const view = renderApp(
      `${SEARCHED_PATH}&required_layout=banquet&required_facilities=PA+system` +
        '&required_accessibility=Step-free+access',
      COORDINATOR,
    )

    const garden = await view.findByRole('article', { name: 'Garden Pavilion' })
    const names = within(resultsList()).getAllByRole('heading', { level: 3 })
    expect(names.map((name) => name.textContent)).toEqual(['Garden Pavilion', 'Harbourfront Hall'])
    expect(garden).toHaveTextContent('Capacity150')
    expect(garden).toHaveTextContent('LocationSentosa')
    expect(garden).toHaveTextContent('Venue ID33')
    const meets = within(garden).getByRole('list', { name: 'Meets' })
    expect(
      within(meets)
        .getAllByRole('listitem')
        .map((item) => item.textContent),
    ).toEqual(['Banquet layout', 'pa system', 'step-free access'])
  })

  it('names a layout the web app does not know yet as the backend spells it', async () => {
    server.use(
      http.post(SEARCH_URL, () =>
        HttpResponse.json({
          results: [
            {
              id: 41,
              name: 'Cabaret Club',
              capacity: 90,
              location: 'Clarke Quay',
              matched_requirements: {
                facilities: [],
                accessibility_features: [],
                layout: 'cabaret',
              },
            },
          ],
        }),
      ),
    )

    renderApp(SEARCHED_PATH, COORDINATOR)

    const club = await screen.findByRole('article', { name: 'Cabaret Club' })
    expect(within(club).getByRole('list', { name: 'Meets' })).toHaveTextContent('cabaret layout')
  })

  it('searches again when a filter changes', async () => {
    const view = renderApp(SEARCHED_PATH, COORDINATOR)
    await view.findByRole('article', { name: 'Garden Pavilion' })

    await typeInto(view, 'Minimum capacity', '200')
    await view.user.click(screen.getByRole('button', { name: 'Search venues' }))

    await waitFor(() =>
      expect(screen.queryByRole('article', { name: 'Garden Pavilion' })).not.toBeInTheDocument(),
    )
    expect(screen.getByRole('article', { name: 'Harbourfront Hall' })).toBeInTheDocument()
  })

  it('lists nothing as met when no requirement was asked for', async () => {
    const view = renderApp(SEARCHED_PATH, COORDINATOR)

    const garden = await view.findByRole('article', { name: 'Garden Pavilion' })

    expect(within(garden).queryByRole('list', { name: 'Meets' })).not.toBeInTheDocument()
  })

  it("shows the backend's message when no venue matches", async () => {
    server.use(
      http.post(SEARCH_URL, () =>
        HttpResponse.json({ results: [], message: 'Nothing here from the backend.' }),
      ),
    )

    renderApp(SEARCHED_PATH, COORDINATOR)

    expect(await screen.findByText('Nothing here from the backend.')).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Venues that match' })).not.toBeInTheDocument()
  })

  it('says it is searching while the results load', () => {
    renderApp(SEARCHED_PATH, COORDINATOR)

    expect(screen.getByText('Searching venues')).toBeInTheDocument()
  })

  it('fills the form from a shared link and runs its search', async () => {
    renderApp(
      `${SEARCHED_PATH}&end_date=2026-11-21&location=Marina&required_facilities=stage`,
      COORDINATOR,
    )

    expect(await screen.findByRole('article', { name: 'Harbourfront Hall' })).toBeInTheDocument()
    expect(screen.getByLabelText('Date')).toHaveValue('2026-11-20')
    expect(screen.getByLabelText('Start time')).toHaveValue('09:00')
    expect(screen.getByLabelText('End time')).toHaveValue('17:00')
    expect(screen.getByLabelText('End date')).toHaveValue('2026-11-21')
    expect(screen.getByLabelText('Minimum capacity')).toHaveValue(120)
    expect(screen.getByLabelText('Location')).toHaveValue('Marina')
    expect(screen.getByLabelText('Facilities')).toHaveValue('stage')
  })

  it("shows the backend's message under the end time, and its summary above the results", async () => {
    const view = renderApp(ROUTES.VENUE_SEARCH, COORDINATOR)

    await search(view, { 'End time': '08:00' })

    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid request.')
    expect(screen.getByLabelText('End time')).toHaveAccessibleDescription(
      'end_time must be after start_time.',
    )
  })

  it("numbers a bad requirement's message by its place in the list", async () => {
    const view = renderApp(ROUTES.VENUE_SEARCH, COORDINATOR)

    await search(view, { Facilities: 'projector{Enter}tables, chairs' })

    await screen.findByRole('alert')
    expect(screen.getByLabelText('Facilities')).toHaveAccessibleDescription(
      'Item 2: Items cannot contain ",".',
    )
  })

  it('shows the start time, capacity, location, layout and list messages under their own fields', async () => {
    server.use(
      http.post(SEARCH_URL, () =>
        validationError({
          start_time: ['Start is wrong.'],
          min_capacity: ['Capacity is wrong.'],
          location: ['Location is wrong.'],
          required_layout: ['Layout is wrong.'],
          required_accessibility: ['Too many.'],
        }),
      ),
    )

    renderApp(SEARCHED_PATH, COORDINATOR)

    await screen.findByRole('alert')
    expect(screen.getByLabelText('Start time')).toHaveAccessibleDescription('Start is wrong.')
    expect(screen.getByLabelText('Minimum capacity')).toHaveAccessibleDescription(
      'Capacity is wrong.',
    )
    expect(screen.getByLabelText('Location')).toHaveAccessibleDescription('Location is wrong.')
    expect(screen.getByLabelText('Room layout')).toHaveAccessibleDescription('Layout is wrong.')
    expect(screen.getByLabelText('Accessibility requirements')).toHaveAccessibleDescription(
      'Too many.',
    )
  })

  it('sends a role other than the Event Coordinator to their own home', async () => {
    const { router } = renderApp(ROUTES.VENUE_SEARCH, {
      session: mockSessionFor(MOCK_ACCOUNTS.venueStaff),
    })

    await screen.findByRole('heading', { level: 1 })
    expect(router.state.location.pathname).toBe(ROUTES.STAFF_HOME)
  })
})

describe('SCRUM-92 finding a replacement venue', () => {
  /**
   * A search for event EVR-BOOK0107's flagged arrangement 9104 at the Lawn Marquee (venue 27):
   * 26 Nov, 1 pm to 5 pm, for 10.
   */
  const REPLACEMENT_PATH =
    `${ROUTES.VENUE_SEARCH}?event=EVR-BOOK0107&replaces=9104&instead_of=27` +
    '&date=2026-11-26&start=13:00&end=17:00&min_capacity=10'

  it('offers each venue found as the replacement, back on the event’s venue requests page', async () => {
    const view = renderApp(REPLACEMENT_PATH, COORDINATOR)

    await view.user.click(
      await screen.findByRole('link', { name: 'Request Boardroom Two as the replacement' }),
    )

    expect(view.router.state.location.pathname).toBe('/events/EVR-BOOK0107/venue-requests')
    expect(view.router.state.location.search).toBe('?replaces=9104&venue=2')
  })

  it('never offers the venue being replaced, as a replacement is always another venue', async () => {
    renderApp(REPLACEMENT_PATH, COORDINATOR)

    const replaced = await screen.findByRole('article', { name: 'Lawn Marquee' })
    expect(within(replaced).queryByRole('link')).not.toBeInTheDocument()
    expect(replaced).toHaveTextContent('This is the venue being replaced.')
    expect(
      screen.getByRole('link', { name: 'Request Boardroom Two as the replacement' }),
    ).toBeInTheDocument()
  })

  it('says which event the replacement is for, with a way back to it', async () => {
    renderApp(REPLACEMENT_PATH, COORDINATOR)

    expect(
      await screen.findByText('Finding a replacement venue for event EVR-BOOK0107.', {
        exact: false,
      }),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to its venue requests' })).toHaveAttribute(
      'href',
      '/events/EVR-BOOK0107/venue-requests',
    )
  })

  it('offers no replacement in an ordinary search', async () => {
    renderApp(SEARCHED_PATH, COORDINATOR)

    await within(await screen.findByRole('list', { name: 'Venues that match' })).findAllByRole(
      'article',
    )
    expect(screen.queryByRole('link', { name: /as the replacement/ })).not.toBeInTheDocument()
    expect(screen.queryByText(/Finding a replacement venue/)).not.toBeInTheDocument()
  })
})
