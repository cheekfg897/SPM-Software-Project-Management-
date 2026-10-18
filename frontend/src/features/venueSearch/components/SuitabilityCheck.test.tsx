import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { ROUTES } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import { MOCK_VENUES } from '@/mocks/handlers/venueFixtures'
import { errorResponse } from '@/mocks/responses'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

const COORDINATOR = { session: mockSessionFor(MOCK_ACCOUNTS.coordinator) }
const ORCHID_ROOM = MOCK_VENUES.orchidRoom
/** 120 people needing step-free access: the Orchid Room holds 100 and has none. */
const SEARCHED_PATH =
  `${ROUTES.VENUE_SEARCH}?date=2026-11-20&start=09:00&end=17:00&min_capacity=120` +
  '&required_accessibility=step-free+access'
const SUITABILITY_URL = '/api/venues/:venueId/suitability'

type View = ReturnType<typeof renderApp>

async function check(view: View, venueName: string) {
  await view.user.selectOptions(await view.findByLabelText('Venue'), venueName)
  await view.user.click(view.getByRole('button', { name: 'Check venue' }))
}

function checksSent(requests: Request[]): Request[] {
  return requests.filter((request) => request.url.endsWith('/suitability'))
}

describe('SCRUM-36 checking a venue against the search', () => {
  it('offers no check before anything has been searched for', async () => {
    renderApp(ROUTES.VENUE_SEARCH, COORDINATOR)

    await screen.findByRole('heading', { level: 1, name: 'Find a venue' })
    expect(screen.queryByRole('heading', { name: 'Check a venue' })).not.toBeInTheDocument()
  })

  it('offers every active venue by name, as the backend lists them', async () => {
    renderApp(SEARCHED_PATH, COORDINATOR)

    const picker = await screen.findByLabelText('Venue')
    await within(picker).findByRole('option', { name: 'Orchid Room' })
    expect(
      within(picker)
        .getAllByRole('option')
        .map((option) => option.textContent),
    ).toEqual([
      'Choose a venue',
      'Boardroom Five',
      'Boardroom Two',
      'Garden Pavilion',
      'Harbourfront Hall',
      'Lawn Marquee',
      'Marina Hall',
      'Orchid Room',
    ])
  })

  it('checks the venue against the needs searched for, and keeps it in the URL', async () => {
    const requests = recordRequests()
    const view = renderApp(SEARCHED_PATH, COORDINATOR)

    await check(view, 'Orchid Room')

    await screen.findByText('Not suitable for this event')
    const sent = checksSent(requests)
    expect(sent.map((request) => new URL(request.url).pathname)).toEqual([
      `/api/venues/${ORCHID_ROOM.id}/suitability`,
    ])
    expect(await sent[0]?.json()).toEqual({
      expected_attendance: 120,
      required_layout: null,
      required_facilities: [],
      required_accessibility: ['step-free access'],
    })
    expect(view.router.state.location.search).toContain(`venue=${ORCHID_ROOM.id}`)
  })

  it('names capacity and the missing accessibility need as why it is unsuitable (AC1, AC2)', async () => {
    const view = renderApp(SEARCHED_PATH, COORDINATOR)

    await check(view, 'Orchid Room')

    const reasons = await screen.findByRole('list', { name: 'Why it is not suitable' })
    expect(
      within(reasons)
        .getAllByRole('listitem')
        .map((item) => item.textContent),
    ).toEqual([
      "Expected attendance of 120 exceeds the venue's capacity of 100.",
      'The venue does not offer step-free access.',
    ])
  })

  it('says a venue meeting every requirement is suitable (AC3)', async () => {
    const view = renderApp(SEARCHED_PATH, COORDINATOR)

    await check(view, 'Harbourfront Hall')

    expect(await screen.findByText('Suitable for this event')).toBeInTheDocument()
    expect(screen.queryByText('Not suitable for this event')).not.toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Why it is not suitable' })).not.toBeInTheDocument()
  })

  it('checks again when the needs change', async () => {
    const view = renderApp(`${SEARCHED_PATH}&venue=${ORCHID_ROOM.id}`, COORDINATOR)
    await screen.findByText('Not suitable for this event')

    await view.user.clear(screen.getByLabelText('Minimum capacity'))
    await view.user.type(screen.getByLabelText('Minimum capacity'), '80')
    await view.user.clear(screen.getByLabelText('Accessibility requirements'))
    await view.user.click(screen.getByRole('button', { name: 'Search venues' }))

    expect(await screen.findByText('Suitable for this event')).toBeInTheDocument()
  })

  it('runs the check from a shared link, with its venue chosen', async () => {
    renderApp(`${SEARCHED_PATH}&venue=${ORCHID_ROOM.id}`, COORDINATOR)

    expect(await screen.findByText('Not suitable for this event')).toBeInTheDocument()
    expect(await screen.findByLabelText('Venue')).toHaveValue(String(ORCHID_ROOM.id))
  })

  it('says it is checking while the answer loads', async () => {
    renderApp(`${SEARCHED_PATH}&venue=${ORCHID_ROOM.id}`, COORDINATOR)

    expect(await screen.findByText('Checking the venue')).toBeInTheDocument()
  })

  it("shows the backend's message when the check is refused", async () => {
    server.use(
      http.post(SUITABILITY_URL, () => errorResponse(404, 'not_found', 'No such venue here.')),
    )

    renderApp(`${SEARCHED_PATH}&venue=${ORCHID_ROOM.id}`, COORDINATOR)

    expect(await screen.findByText('No such venue here.')).toBeInTheDocument()
  })

  it("shows the backend's message when the venues cannot be listed", async () => {
    server.use(
      http.get('/api/venues', () =>
        HttpResponse.json(
          { error: 'server_error', message: 'Venues are resting.' },
          { status: 500 },
        ),
      ),
    )

    renderApp(SEARCHED_PATH, COORDINATOR)

    expect(await screen.findByText('Venues are resting.')).toBeInTheDocument()
  })
})
