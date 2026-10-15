import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { ROUTES } from '@/config/routes'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

import {
  CATALOGUE_URL,
  catalogueEvent,
  cataloguePage,
  catalogueQueries,
  respondWithPage,
} from '../test/catalogueResponses'

function lastOf(queries: string[]): string | undefined {
  return queries[queries.length - 1]
}

function eventCard(name: string): HTMLElement {
  const card = screen.getByRole('heading', { name }).closest('article')
  if (card === null) {
    throw new Error(`${name} is not inside an article.`)
  }
  return card
}

describe('SCRUM-52 catalogue page: what the backend sent', () => {
  it('shows the events grouped by day, with the total and page count from the backend', async () => {
    respondWithPage(
      cataloguePage({
        items: [
          catalogueEvent({ name: 'Jazz by the Bay', starts_at: '2026-10-05T19:30:00+08:00' }),
          catalogueEvent({
            name: 'Pitch Night',
            starts_at: '2026-10-07T19:00:00+08:00',
            ends_at: '2026-10-07T21:30:00+08:00',
          }),
        ],
        total: 31,
        total_pages: 3,
      }),
    )

    renderApp(ROUTES.EVENTS)

    expect(await screen.findByRole('heading', { name: 'Jazz by the Bay' })).toBeInTheDocument()
    expect(screen.getByText('31 events')).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Pagination' })).toHaveTextContent('Page 1 of 3')
    expect(screen.getByRole('heading', { name: 'Monday 5 Oct' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Wednesday 7 Oct' })).toBeInTheDocument()
    expect(within(eventCard('Pitch Night')).getByText('7:00 pm – 9:30 pm')).toBeInTheDocument()
  })

  it("shows each event's venue and places as the backend counts them", async () => {
    respondWithPage(
      cataloguePage({
        items: [
          catalogueEvent({ name: 'Open', places_left: 12 }),
          catalogueEvent({ name: 'Last seat', places_left: 1 }),
          catalogueEvent({ name: 'Sold out', places_left: 0, is_full: true }),
          catalogueEvent({ name: 'Mine', is_registered: true }),
          catalogueEvent({ name: 'Somewhere', venue: null }),
        ],
        total: 5,
        total_pages: 1,
      }),
    )

    renderApp(ROUTES.EVENTS)

    await screen.findByRole('heading', { name: 'Open' })
    expect(within(eventCard('Open')).getByText('12 places left')).toBeInTheDocument()
    expect(within(eventCard('Open')).getByText('Esplanade Outdoor Theatre')).toBeInTheDocument()
    expect(within(eventCard('Last seat')).getByText('1 place left')).toBeInTheDocument()
    expect(within(eventCard('Sold out')).getByText('Full')).toBeInTheDocument()
    expect(within(eventCard('Mine')).getByText("You're registered")).toBeInTheDocument()
    expect(within(eventCard('Somewhere')).getByText('Venue to be announced')).toBeInTheDocument()
    expect(screen.getByText('5 events')).toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: 'Pagination' })).not.toBeInTheDocument()
  })

  it('links an event the attendee holds a place at to their own events, and no other', async () => {
    respondWithPage(
      cataloguePage({
        items: [
          catalogueEvent({ name: 'Mine', is_registered: true }),
          catalogueEvent({ name: 'Open' }),
        ],
        total: 2,
        total_pages: 1,
      }),
    )

    renderApp(ROUTES.EVENTS)

    await screen.findByRole('heading', { name: 'Mine' })
    expect(
      within(eventCard('Mine')).getByRole('link', { name: 'View in My events' }),
    ).toHaveAttribute('href', ROUTES.MY_EVENTS)
    expect(
      within(eventCard('Open')).queryByRole('link', { name: 'View in My events' }),
    ).not.toBeInTheDocument()
  })

  it('says "1 event" for a single result', async () => {
    respondWithPage(cataloguePage({ items: [catalogueEvent()], total: 1, total_pages: 1 }))

    renderApp(ROUTES.EVENTS)

    expect(await screen.findByText('1 event')).toBeInTheDocument()
  })

  it('says it is loading until the backend answers', () => {
    server.use(http.get(CATALOGUE_URL, () => new Promise<never>(() => undefined)))

    renderApp(ROUTES.EVENTS)

    expect(screen.getByRole('status')).toHaveTextContent('Loading events')
  })

  it('shows the backend error and tries again when asked', async () => {
    // The newest handler answers first: the 500 once, then the page.
    respondWithPage(
      cataloguePage({ items: [catalogueEvent({ name: 'Back again' })], total: 1, total_pages: 1 }),
    )
    server.use(
      http.get(
        CATALOGUE_URL,
        () =>
          HttpResponse.json(
            { error: 'internal_error', message: 'The catalogue is resting.' },
            { status: 500 },
          ),
        { once: true },
      ),
    )
    const { user } = renderApp(ROUTES.EVENTS)

    expect(await screen.findByRole('alert')).toHaveTextContent('The catalogue is resting.')
    await user.click(screen.getByRole('button', { name: 'Try again' }))

    expect(await screen.findByRole('heading', { name: 'Back again' })).toBeInTheDocument()
  })

  it('offers to clear the filters when nothing matches them', async () => {
    respondWithPage(cataloguePage())
    const { user, router } = renderApp(`${ROUTES.EVENTS}?q=zzz&when=today`)

    expect(await screen.findByText('No events match your filters.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Clear filters' }))

    expect(router.state.location.search).toBe('')
  })

  it('says nothing is open yet when there are no events and no filters', async () => {
    respondWithPage(cataloguePage())

    renderApp(ROUTES.EVENTS)

    expect(await screen.findByText('No events are open for registration yet.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Clear filters' })).not.toBeInTheDocument()
  })
})

describe('SCRUM-52 catalogue page: the URL is what gets asked for', () => {
  it("sends the URL's filters to the backend as they are", async () => {
    const requests = recordRequests()

    renderApp(`${ROUTES.EVENTS}?q=jazz&when=today&page=2`)

    await waitFor(() => expect(lastOf(catalogueQueries(requests))).toBe('q=jazz&when=today&page=2'))
  })

  it('searches as you type, from the first page', async () => {
    const requests = recordRequests()
    const { user, router } = renderApp(`${ROUTES.EVENTS}?page=2`)

    await user.type(screen.getByRole('searchbox', { name: 'Search events' }), 'jazz')

    await waitFor(() => expect(router.state.location.search).toBe('?q=jazz'))
    await waitFor(() => expect(lastOf(catalogueQueries(requests))).toBe('q=jazz'))
  })

  it('shows the search from the URL, and empties the box when the filters are cleared', async () => {
    respondWithPage(cataloguePage())
    const { user } = renderApp(`${ROUTES.EVENTS}?q=zzz`)
    const searchBox = screen.getByRole('searchbox', { name: 'Search events' })
    expect(searchBox).toHaveValue('zzz')

    await user.click(await screen.findByRole('button', { name: 'Clear filters' }))

    expect(searchBox).toHaveValue('')
  })

  it('asks for a preset window when one is chosen', async () => {
    const requests = recordRequests()
    const { user, router } = renderApp(ROUTES.EVENTS)
    expect(screen.getByRole('radio', { name: 'Upcoming' })).toBeChecked()

    await user.click(screen.getByRole('radio', { name: 'This week' }))

    expect(router.state.location.search).toBe('?when=this_week')
    await waitFor(() => expect(lastOf(catalogueQueries(requests))).toBe('when=this_week'))
  })

  it('swaps the preset for a custom range when dates are picked', async () => {
    const requests = recordRequests()
    const { user, router } = renderApp(`${ROUTES.EVENTS}?when=today`)

    await user.click(screen.getByRole('radio', { name: 'Pick dates' }))
    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-10-20T09:00' } })
    fireEvent.change(screen.getByLabelText('To'), { target: { value: '2026-10-25T18:00' } })

    expect(router.state.location.search).toBe(
      '?starts_from=2026-10-20T09%3A00&starts_to=2026-10-25T18%3A00',
    )
    await waitFor(() =>
      expect(lastOf(catalogueQueries(requests))).toBe(
        'starts_from=2026-10-20T09%3A00&starts_to=2026-10-25T18%3A00',
      ),
    )
    expect(screen.getByRole('radio', { name: 'Pick dates' })).toBeChecked()
  })

  it('hides the dates again when a preset is chosen', async () => {
    const { user, router } = renderApp(`${ROUTES.EVENTS}?starts_from=2026-10-20T09%3A00`)
    expect(screen.getByLabelText('From')).toHaveValue('2026-10-20T09:00')

    await user.click(screen.getByRole('radio', { name: 'Today' }))

    expect(router.state.location.search).toBe('?when=today')
    expect(screen.queryByLabelText('From')).not.toBeInTheDocument()
  })

  it("shows the backend's messages next to the dates it refused", async () => {
    renderApp(`${ROUTES.EVENTS}?starts_from=2026-10-25T00%3A00&starts_to=2026-10-20T00%3A00`)

    await waitFor(() =>
      expect(screen.getByLabelText('To')).toHaveAccessibleDescription('Must be after starts_from.'),
    )
    expect(screen.getByRole('alert')).toHaveTextContent('Invalid request.')
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument()
  })

  it('moves between pages, back to the top, keeping the last page on screen until the next arrives', async () => {
    const scrollTo = vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined)
    respondWithPage(
      cataloguePage({
        items: [catalogueEvent({ name: 'On page one' })],
        total: 30,
        total_pages: 3,
      }),
    )
    const { user, router } = renderApp(ROUTES.EVENTS)
    await screen.findByRole('heading', { name: 'On page one' })
    server.use(http.get(CATALOGUE_URL, () => new Promise<never>(() => undefined)))

    await user.click(screen.getByRole('button', { name: 'Next page' }))

    expect(router.state.location.search).toBe('?page=2')
    expect(scrollTo).toHaveBeenCalled()
    expect(screen.getByRole('heading', { name: 'On page one' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Results' })).toHaveAttribute('aria-busy', 'true')
  })
})
