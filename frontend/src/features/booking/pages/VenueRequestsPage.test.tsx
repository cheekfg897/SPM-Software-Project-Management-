import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { ROUTES } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/handlers/auth'
import { MOCK_BOOKING_EVENTS, MOCK_BOOKING_VENUES } from '@/mocks/handlers/bookingFixtures'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

import type { BookingRequest } from '../api'

const APPROVED_PATH = `/events/${MOCK_BOOKING_EVENTS.approved.id}/venue-requests`
const SESSION = { session: mockSessionFor(MOCK_ACCOUNTS.coordinator) }
const BOOKING_URL = '/api/venues/events/:eventId/booking-requests'

const EXISTING_REQUEST: BookingRequest = {
  id: 7,
  event_id: MOCK_BOOKING_EVENTS.approved.id,
  venue_id: 5,
  starts_at: '2026-11-10T09:00:00+08:00',
  ends_at: '2026-11-10T12:00:00+08:00',
  purpose: 'Opening keynote',
  expected_occupancy: 80,
  required_layout: 'theatre',
  justification: null,
  status: 'pending',
  event_proposed_date: '2026-11-10',
  event_end_date: null,
  event_start_time: '09:00:00',
  event_end_time: '17:00:00',
  accessibility_needs: 'Step-free access',
}

/** Type into a field from scratch: after a form reset, user-event still remembers the old text. */
async function typeInto(view: ReturnType<typeof renderApp>, label: string, text: string) {
  const field = await view.findByLabelText(label)
  await view.user.clear(field)
  await view.user.type(field, text)
}

/** Fill the required fields; the venue is the one id the form needs. */
async function fillRequest(view: ReturnType<typeof renderApp>, venueId: number) {
  await typeInto(view, 'Venue ID', String(venueId))
  await typeInto(view, 'Starts', '2026-11-10T09:00')
  await typeInto(view, 'Ends', '2026-11-10T12:00')
  await typeInto(view, 'Purpose', 'Keynote')
}

describe('SCRUM-42 venue requests page', () => {
  it('shows the not-found page, and asks for nothing, when the event id is not a number', () => {
    const requests = recordRequests()

    renderApp('/events/abc/venue-requests', SESSION)

    expect(screen.getByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
    expect(requests).toHaveLength(0)
  })

  it('says what is loading while the requests are read', () => {
    renderApp(APPROVED_PATH, SESSION)

    expect(screen.getByText('Loading venue requests')).toBeInTheDocument()
  })

  it('says so when the event has no requests yet', async () => {
    renderApp(APPROVED_PATH, SESSION)

    expect(await screen.findByText('No venue requests yet.')).toBeInTheDocument()
  })

  it('shows each request with its status, event timing and accessibility needs', async () => {
    server.use(http.get(BOOKING_URL, () => HttpResponse.json([EXISTING_REQUEST])))

    renderApp(APPROVED_PATH, SESSION)

    const item = await screen.findByRole('listitem', { name: /Opening keynote/ })
    const text = item.textContent ?? ''
    expect(text).toContain('Venue 5')
    expect(text).toContain('Pending')
    expect(text).toContain('80 guests')
    expect(text).toContain('Theatre')
    expect(text).toContain('9:00 am – 12:00 pm')
    expect(text).toContain('2026-11-10')
    expect(text).toContain('09:00:00')
    expect(text).toContain('Step-free access')
  })

  it('shows a multi-day event with its end date, and leaves out accessibility needs it has none of', async () => {
    const multiDay = {
      ...EXISTING_REQUEST,
      event_end_date: '2026-11-12',
      accessibility_needs: null,
    }
    server.use(http.get(BOOKING_URL, () => HttpResponse.json([multiDay])))

    renderApp(APPROVED_PATH, SESSION)

    const item = await screen.findByRole('listitem', { name: /Opening keynote/ })
    expect(item).toHaveTextContent('2026-11-10 to 2026-11-12')
    expect(item).not.toHaveTextContent('Accessibility')
  })

  it('sends the typed request, then lists it as pending', async () => {
    const requests = recordRequests()
    const view = renderApp(APPROVED_PATH, SESSION)
    await fillRequest(view, MOCK_BOOKING_VENUES.roomy.id)

    await view.user.click(view.getByRole('button', { name: 'Request venue' }))

    const item = await screen.findByRole('listitem', { name: /Keynote/ })
    expect(within(item).getByText('Pending')).toBeInTheDocument()
    const post = requests.find((request) => request.method === 'POST')
    expect(await post?.json()).toEqual({
      venue_id: MOCK_BOOKING_VENUES.roomy.id,
      starts_at: '2026-11-10T09:00:00+08:00',
      ends_at: '2026-11-10T12:00:00+08:00',
      purpose: 'Keynote',
    })
    await waitFor(() => expect(view.getByLabelText('Purpose')).toHaveValue(''))
  })

  it('sends the occupancy, layout and justification when they are filled in', async () => {
    const requests = recordRequests()
    const view = renderApp(APPROVED_PATH, SESSION)
    await fillRequest(view, MOCK_BOOKING_VENUES.tiny.id)
    await view.user.type(view.getByLabelText('Expected occupancy'), '15')
    await view.user.selectOptions(view.getByLabelText('Required layout'), 'Banquet')
    await view.user.type(view.getByLabelText('Justification'), 'Only room free')

    await view.user.click(view.getByRole('button', { name: 'Request venue' }))

    await screen.findByRole('listitem', { name: /Keynote/ })
    const post = requests.find((request) => request.method === 'POST')
    expect(await post?.json()).toMatchObject({
      expected_occupancy: 15,
      required_layout: 'banquet',
      justification: 'Only room free',
    })
  })

  it("shows the backend's message against the justification input", async () => {
    const view = renderApp(APPROVED_PATH, SESSION)
    await fillRequest(view, MOCK_BOOKING_VENUES.tiny.id)

    await view.user.click(view.getByRole('button', { name: 'Request venue' }))

    expect(await view.findByLabelText('Justification')).toHaveAccessibleDescription(
      'A justification is required because the venue is not suitable.',
    )
    expect(view.getByLabelText('Purpose')).toHaveAccessibleDescription('')
  })

  it('shows a refusal that belongs to the whole request, such as a duplicate', async () => {
    const view = renderApp(APPROVED_PATH, SESSION)
    await fillRequest(view, MOCK_BOOKING_VENUES.roomy.id)
    await view.user.click(view.getByRole('button', { name: 'Request venue' }))
    await screen.findByRole('listitem', { name: /Keynote/ })
    await waitFor(() => expect(view.getByLabelText('Purpose')).toHaveValue(''))
    await fillRequest(view, MOCK_BOOKING_VENUES.roomy.id)

    await view.user.click(view.getByRole('button', { name: 'Request venue' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'A pending request for this event, venue and period already exists.',
    )
  })

  it('shows the backend message when the event is not found', async () => {
    renderApp(`/events/${MOCK_BOOKING_EVENTS.someoneElses.id}/venue-requests`, SESSION)

    expect(await screen.findByRole('alert')).toHaveTextContent('Event not found.')
  })

  it('shows the backend message when the event is not approved', async () => {
    const view = renderApp(`/events/${MOCK_BOOKING_EVENTS.confirmed.id}/venue-requests`, SESSION)
    await fillRequest(view, MOCK_BOOKING_VENUES.roomy.id)

    await view.user.click(view.getByRole('button', { name: 'Request venue' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Only an approved event can have a venue booking request; this one is confirmed.',
    )
  })

  it('sends someone who is not a coordinator to their own home', async () => {
    const { router } = renderApp(APPROVED_PATH, {
      session: mockSessionFor(MOCK_ACCOUNTS.attendee),
    })

    await screen.findByRole('heading', { level: 1 })
    expect(router.state.location.pathname).toBe(ROUTES.EVENTS)
    expect(screen.queryByLabelText('Venue ID')).not.toBeInTheDocument()
  })

  it('sends a visitor to the staff log-in page, remembering the page', async () => {
    const { router } = renderApp(APPROVED_PATH)

    await screen.findByRole('heading', { name: 'Staff log in' })
    expect(router.state.location.pathname).toBe(ROUTES.STAFF_LOGIN)
    expect(router.state.location.search).toContain(encodeURIComponent(APPROVED_PATH))
  })
})
